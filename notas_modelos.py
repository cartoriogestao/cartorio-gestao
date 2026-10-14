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


def _corpo(texto: str) -> str:
    """Junta o modelo escrito em varias linhas num paragrafo unico.

    O modelo e escrito quebrado no codigo, para caber na tela de quem o mantem;
    o ato sai corrido, como manda o art. 795, § 2º, do Codigo de Normas.
    """
    return re.sub(r"\s*\n\s*", " ", texto.strip())


MODELOS: list[dict] = [

    # =================================================== ESCRITURAS

    {
        "codigo": "NT-ESC-COMPRA-VENDA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de compra e venda de imóvel urbano",
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
        "corpo": _corpo("""<p>Saibam quantos este público
instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês
de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, {ONDE FOI LIDA: nesta
serventia, situada na sede | no endereço [ENDEREÇO COMPLETO DA LAVRATURA], para
onde me desloquei a pedido das partes}, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram as partes entre si justas e contratadas, a
saber: como OUTORGANTE VENDEDOR, {{ outorgantes }}; e como OUTORGADO COMPRADOR,
{{ outorgados }}; todos reconhecidos como os próprios por mim, tabelião, à vista
dos documentos apresentados, e declarando possuir capacidade civil,
legitimidade e livre manifestação de vontade para a prática deste ato, do que
dou fé. I - DO IMÓVEL OBJETO DA COMPRA E VENDA: Pelo OUTORGANTE VENDEDOR foi
declarado que é senhor e legítimo possuidor do imóvel a seguir descrito:
[DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA, COM CARACTERÍSTICAS, CONFRONTAÇÕES E
LOCALIZAÇÃO], com inscrição cadastral n. [INSCRIÇÃO CADASTRAL] junto à
Prefeitura Municipal. «SE EDIFICADO: O imóvel é edificado e recebe o número
predial [NÚMERO PREDIAL] da [RUA DO IMÓVEL].» II - DA MATRÍCULA, DO TÍTULO
AQUISITIVO E DA SITUAÇÃO REGISTRAL: O imóvel encontra-se matriculado sob o n.
[MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS], figurando como titular o
OUTORGANTE VENDEDOR, e tendo como registro anterior [NATUREZA E NÚMERO DO
REGISTRO ANTERIOR]. A alienação compreenderá a integralidade do imóvel, com
suas benfeitorias, acessões, servidões, direitos e ações. III - DO PREÇO, DA
FORMA DE PAGAMENTO E DA QUITAÇÃO: Pelo presente instrumento e na melhor forma
de direito, o OUTORGANTE VENDEDOR vende, como de fato vendido tem, o imóvel
acima descrito ao OUTORGADO COMPRADOR, pelo preço certo e ajustado de
[PREÇO POR EXTENSO] ([PREÇO EM ALGARISMOS]), que declara haver recebido
{FORMA DE PAGAMENTO: em dinheiro em espécie | por transferência bancária | por
transferência eletrônica entre contas de pagamento | por PIX | mediante cheque
n. [NÚMERO DO CHEQUE], sacado contra o [BANCO DO CHEQUE]}, dando ao OUTORGADO
COMPRADOR, pelo preço recebido, plena, geral, irrevogável e irretratável
quitação, para nada mais reclamar a esse título. As partes declaram, sob
responsabilidade civil e penal, que o preço e a forma de pagamento ora
consignados correspondem à realidade econômica do negócio, tendo sido
advertidas acerca dos deveres de informação, transparência e prevenção à
lavagem de dinheiro e ao financiamento do terrorismo. IV - DO ITBI, DO INSS E
DOS TRIBUTOS: Foi apresentado o comprovante de recolhimento do ITBI, guia n.
[NÚMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI], no valor de
[VALOR DO ITBI]. «SE ISENÇÃO OU IMUNIDADE: reconhecida pela autoridade
fazendária a {BENEFÍCIO: isenção | imunidade} de ITBI, conforme
[DOCUMENTO DO RECONHECIMENTO].» {INSS: As partes declaram não estar sujeitas às
contribuições previdenciárias de que trata o artigo 47 da Lei n. 8.212, de
1991 | Foi apresentada a Certidão Negativa de Débitos do INSS n.
[NÚMERO DA CND], expedida em [DATA DA CND]}. O OUTORGANTE VENDEDOR responde
pelos tributos e encargos cujo fato gerador seja anterior à tradição, cabendo
ao OUTORGADO COMPRADOR os posteriores, ressalvada disposição legal ou ajuste
expresso diverso. V - DA MODALIDADE DA VENDA, AD CORPUS, POSSE E EVICÇÃO: A
presente compra e venda é celebrada na modalidade AD CORPUS, abrangendo a
integralidade do imóvel objeto da matrícula acima referida, tomando-se a
descrição, os limites e confrontações constantes do fólio real como elementos
de identificação jurídica do objeto, sem vinculação do preço à unidade de
medida. Em razão desta venda, o OUTORGANTE VENDEDOR transmite ao OUTORGADO
COMPRADOR todo o domínio, direito, posse e ação que exercia sobre o imóvel,
obrigando-se por si e seus sucessores a fazer esta venda sempre boa, firme e
valiosa e a responder pela evicção de direito, na forma dos artigos 447 e
seguintes do Código Civil. «SE POSSE ANTERIOR AO ATO: As partes declaram que a
posse foi transmitida ao comprador em
[DATA OU ÉPOCA DA TRANSMISSÃO DA POSSE], permanecendo ele desde então imitido
na posse do imóvel.» VI - DAS DECLARAÇÕES DO OUTORGANTE VENDEDOR: O OUTORGANTE
VENDEDOR declara, sob responsabilidade civil e penal: a) que possui
legitimidade e disponibilidade jurídica para a alienação; b) que, ressalvado o
que resultar da certidão atualizada da matrícula e das consultas obrigatórias,
o imóvel encontra-se livre de ônus, gravames, constrições, indisponibilidades
ou direitos de terceiros incompatíveis com a venda; c) que não celebrou
promessa, cessão, locação, comodato ou outro negócio incompatível com a
transmissão ora formalizada; d) que não tem conhecimento de demanda, litígio ou
ato de autoridade que impeça a alienação; e) que as informações prestadas
acerca do preço, do pagamento e da posse são verdadeiras; e f) que responde por
fatos, débitos e obrigações anteriores à tradição nos limites da lei. VII - DAS
DECLARAÇÕES DO OUTORGADO COMPRADOR: Pelo OUTORGADO COMPRADOR me foi dito que
examinou o imóvel, sua localização, situação física, confrontações, acessos,
benfeitorias e a descrição constante da matrícula, aceitando-o no estado em que
se encontra, sem prejuízo da responsabilidade legal do OUTORGANTE VENDEDOR pela
evicção e por fatos anteriores ao negócio. Declara ciência de que a propriedade
imóvel somente se transfere com o registro deste título no Registro de Imóveis
competente, na forma do artigo 1.245 do Código Civil, e autoriza a apresentação
do traslado ao Registro de Imóveis. VIII - DAS CERTIDÕES, CONSULTAS E DOCUMENTOS
ARQUIVADOS: Foram apresentados e ficam arquivados nesta serventia, física ou
eletronicamente, conforme aplicável: os documentos de identificação e, se
casados, as certidões de casamento dos comparecentes; a certidão atualizada da
matrícula, expedida em [DATA DA CERTIDÃO DA MATRÍCULA]; e a certidão de
propriedade e de ônus reais. «SE HOUVE CONSULTA À CNIB: Procedeu-se à consulta
prévia à Central Nacional de Indisponibilidade de Bens sobre o OUTORGANTE
VENDEDOR, sob o protocolo/hash [PROTOCOLO OU HASH DA CONSULTA À CNIB], nada
constando em desfavor.» Quanto às certidões judiciais e administrativas não
legalmente indispensáveis, o OUTORGADO COMPRADOR declara ter sido informado
acerca de sua possibilidade e DISPENSA EXPRESSAMENTE SUA APRESENTAÇÃO,
ASSUMINDO OS RISCOS DECORRENTES DA DISPENSA. IX - DA PUBLICIDADE, DA DOI, DA
LGPD E DA PREVENÇÃO À LAVAGEM DE DINHEIRO: Fica consignado que será emitida a
Declaração sobre Operação Imobiliária (DOI), nos termos do artigo 8º da Lei n.
10.426, de 2002. Os comparecentes declaram ciência de que seus dados pessoais
serão tratados na medida necessária ao cumprimento das atribuições legais e
regulamentares da atividade notarial e registral, inclusive para qualificação,
lavratura, arquivamento, emissão de selos, comunicações obrigatórias,
fiscalização e registro, na forma da Lei n. 13.709/2018. Foram observadas as
normas de prevenção à lavagem de dinheiro e ao financiamento do terrorismo,
tendo as partes sido advertidas de que respondem pela exatidão das declarações
acerca de preço, forma de pagamento, origem dos recursos, beneficiários e
demais informações prestadas. X - DA BASE LEGAL, DA LEITURA E DO CONSENTIMENTO:
A presente escritura é lavrada com fundamento nos artigos 108, 215, 481 e
seguintes e 1.245 do Código Civil, na Lei n. 6.015/1973, na Lei n. 7.433/1985 e
no Decreto n. 93.240/1986, no Código Nacional de Normas do Foro Extrajudicial,
instituído pelo Provimento CNJ n. 149/2023 e suas alterações, e no Código de
Normas do Foro Extrajudicial do Maranhão. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-COMPRA-VENDA-RURAL",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de compra e venda de imóvel rural",
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
        "corpo": _corpo("""<p>Saibam quantos
este público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS])
dias do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO]
([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }}, Estado do
{{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram as partes entre si justas e contratadas, a
saber: como OUTORGANTE VENDEDOR, {{ outorgantes }}; e como OUTORGADO
COMPRADOR, {{ outorgados }}; todos reconhecidos como os próprios por mim,
tabelião, à vista dos documentos apresentados, e declarando possuir capacidade
civil, legitimidade e livre manifestação de vontade para a prática deste ato,
do que dou fé. I - DO IMÓVEL OBJETO DA COMPRA E VENDA: Pelo OUTORGANTE VENDEDOR
foi declarado que é senhor e legítimo possuidor do imóvel rural denominado
[DENOMINAÇÃO DO IMÓVEL], situado em [LOCALIZAÇÃO DO IMÓVEL], com área de
[ÁREA POR EXTENSO] ([ÁREA EM ALGARISMOS]) hectares e perímetro de
[PERÍMETRO], assim descrito e caracterizado: [DESCRIÇÃO DO IMÓVEL COM
CONFRONTAÇÕES]. «SE GEORREFERENCIADO: Todas as coordenadas estão
georreferenciadas ao Sistema Geodésico Brasileiro, datum SIRGAS2000, conforme
planta, memorial descritivo e Termo de Responsabilidade Técnica n.
[NÚMERO DO TRT], elaborados por [NOME DO TÉCNICO], Conselho
[CONSELHO DO TÉCNICO] n. [NÚMERO NO CONSELHO], credenciado no INCRA sob o n.
[CREDENCIAMENTO NO INCRA].» II - DA MATRÍCULA, DO TÍTULO AQUISITIVO E DA
SITUAÇÃO REGISTRAL: O imóvel encontra-se matriculado sob o n. [MATRÍCULA] do
[CARTÓRIO DE REGISTRO DE IMÓVEIS], figurando como titular o OUTORGANTE
VENDEDOR, e tendo como registro anterior
[NATUREZA E NÚMERO DO REGISTRO ANTERIOR]. A alienação compreenderá a
integralidade do imóvel, com suas benfeitorias, acessões, servidões, direitos e
ações. III - DO PREÇO, DA FORMA DE PAGAMENTO E DA QUITAÇÃO: Pelo presente
instrumento e na melhor forma de direito, o OUTORGANTE VENDEDOR vende o imóvel
acima descrito ao OUTORGADO COMPRADOR, pelo preço certo e ajustado de
[PREÇO POR EXTENSO] ([PREÇO EM ALGARISMOS]), que declara haver recebido
{FORMA DE PAGAMENTO: em dinheiro em espécie | por transferência bancária | por
transferência eletrônica entre contas de pagamento | por PIX | mediante cheque
n. [NÚMERO DO CHEQUE], sacado contra o [BANCO DO CHEQUE]}, dando ao OUTORGADO
COMPRADOR, pelo preço recebido, plena, geral, irrevogável e irretratável
quitação, para nada mais reclamar a esse título. As partes declaram, sob
responsabilidade civil e penal, que o preço e a forma de pagamento ora
consignados correspondem à realidade econômica do negócio, tendo sido
advertidas acerca dos deveres de informação, transparência e prevenção à
lavagem de dinheiro e ao financiamento do terrorismo. IV - DO ITBI E DOS
TRIBUTOS: Foi apresentado o comprovante de recolhimento do ITBI, guia n.
[NÚMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI], no valor de
[VALOR DO ITBI]. «SE ISENÇÃO OU IMUNIDADE: reconhecida pela autoridade
fazendária a {BENEFÍCIO: isenção | imunidade} de ITBI, conforme
[DOCUMENTO DO RECONHECIMENTO].» O OUTORGANTE VENDEDOR responde pelos tributos
e encargos cujo fato gerador seja anterior à tradição, cabendo ao OUTORGADO
COMPRADOR os posteriores, ressalvada disposição legal ou ajuste expresso
diverso. V - DO CCIR, DO ITR, DO CAR E DA IDENTIFICAÇÃO CADASTRAL RURAL: Foi
apresentado o Certificado de Cadastro de Imóvel Rural - CCIR, exercício
[EXERCÍCIO DO CCIR], código do imóvel n. [CÓDIGO DO IMÓVEL NO INCRA], do qual
transcrevo resumidamente, na forma do artigo 802, § 5º, do Código de Normas:
detentor [NOME DO DETENTOR], de nacionalidade [NACIONALIDADE DO DETENTOR];
denominação [DENOMINAÇÃO NO CCIR]; área total de [ÁREA DO CCIR] e módulo
fiscal de [MÓDULO FISCAL] — documento sem o qual o proprietário não pode
desmembrar, arrendar, hipotecar, vender nem prometer em venda o imóvel rural,
SOB PENA DE NULIDADE, na forma do artigo 802, § 3º, do Código de Normas e do
artigo 22, § 1º, da Lei n. 4.947/1966. Foi igualmente apresentada a
comprovação de quitação do Imposto sobre a Propriedade Territorial Rural dos
cinco últimos exercícios, {ITR: mediante os recibos de pagamento referentes
aos exercícios de [EXERCÍCIOS DO ITR] | mediante Certidão de Quitação de
Tributos e Contribuições Federais n. [NÚMERO DA CERTIDÃO DE QUITAÇÃO],
expedida em [DATA DA CERTIDÃO DE QUITAÇÃO] | sendo o imóvel pequena gleba
rural de até trinta hectares, explorada pelo proprietário que não possui outro
imóvel, hipótese de não incidência do artigo 20 da Lei n. 9.393/1996}.
«SE CAR: Foi apresentado o Recibo de Inscrição do Imóvel Rural no Cadastro
Ambiental Rural - CAR n. [NÚMERO DO CAR], relativo a [DENOMINAÇÃO NO CAR],
área total declarada de [ÁREA DO CAR] hectares, em nome de
[DETENTOR NO CAR].» «SE DIVERGÊNCIA CADASTRAL: Os documentos cadastrais
apresentam denominação, área ou referências distintas da matrícula, o que não
impede o registro do presente título — o CCIR, o CAR e a certidão do ITR
possuem natureza cadastral e fiscal própria, não substituem a especialidade
objetiva do Registro de Imóveis e poderão demandar atualização perante o
INCRA/SNCR/CNIR, a Receita Federal e o órgão ambiental competente após o
registro da transmissão.» VI - DA MODALIDADE DA VENDA, AD CORPUS, POSSE E
EVICÇÃO: A presente compra e venda é celebrada na modalidade AD CORPUS,
abrangendo a integralidade do imóvel objeto da matrícula acima referida,
tomando-se a descrição, os limites, confrontações, área e perímetro constantes
do fólio real como elementos de identificação jurídica do objeto, sem
vinculação do preço à unidade de medida. Em razão desta venda, o OUTORGANTE
VENDEDOR cede e transfere ao OUTORGADO COMPRADOR todo o domínio, direito, ação
e posse que exerce sobre o imóvel, obrigando-se por si e seus sucessores a
fazer a presente venda sempre boa, firme e valiosa e a responder pela evicção
de direito, na forma dos artigos 447 e seguintes do Código Civil.
«SE POSSE ANTERIOR AO ATO: As partes declaram que a posse foi transmitida ao
comprador em [DATA OU ÉPOCA DA TRANSMISSÃO DA POSSE], permanecendo ele desde
então imitido na posse do imóvel.» VII - DO GEORREFERENCIAMENTO, DA
ESPECIALIDADE E DO REGISTRO: «SE GEORREFERENCIADO: As partes declaram ciência
de que a descrição acima é georreferenciada ao Sistema Geodésico Brasileiro,
datum SIRGAS2000, e o OUTORGANTE VENDEDOR compromete-se a prestar colaboração
razoável e a assinar documentos que dependam de sua atuação como antigo
titular para eventuais atualizações cadastrais posteriores, desde que tal
providência não lhe imponha nova obrigação econômica nem altere o preço ou a
substância do negócio.» A presente transmissão é lavrada segundo a descrição
registral vigente. VIII - DAS DECLARAÇÕES DO OUTORGANTE VENDEDOR: O
OUTORGANTE VENDEDOR declara, sob responsabilidade civil e penal: a) que possui
legitimidade e disponibilidade jurídica para a alienação; b) que, ressalvado o
que resultar da certidão atualizada da matrícula e das consultas obrigatórias,
o imóvel encontra-se livre de ônus, gravames, constrições, indisponibilidades
ou direitos de terceiros incompatíveis com a venda; c) que não celebrou
promessa, cessão, arrendamento, parceria, comodato ou outro negócio
incompatível com a transmissão ora formalizada; d) que não tem conhecimento de
demanda, conflito possessório, restrição ambiental ou ato de autoridade que
impeça a alienação; e) que as informações prestadas acerca do preço, da posse
e da situação cadastral são verdadeiras; e f) que responde por fatos, débitos
e obrigações anteriores à tradição nos limites da lei. IX - DAS DECLARAÇÕES DO
OUTORGADO COMPRADOR: Pelo OUTORGADO COMPRADOR me foi dito que examinou o
imóvel, sua localização, situação física, confrontações, acessos,
benfeitorias, documentos cadastrais e fiscais e a descrição constante da
matrícula, aceitando-o no estado em que se encontra, sem prejuízo da
responsabilidade legal do OUTORGANTE VENDEDOR pela evicção e por fatos
anteriores ao negócio. Declara ciência de que a propriedade imóvel somente se
transfere com o registro deste título no Registro de Imóveis competente, na
forma do artigo 1.245 do Código Civil, e autoriza a apresentação do traslado
ao Registro de Imóveis, bem como a prática dos atos cadastrais complementares
necessários após o registro. X - DAS CERTIDÕES, CONSULTAS E DOCUMENTOS
ARQUIVADOS: Foram apresentados e ficam arquivados nesta serventia, física ou
eletronicamente, conforme aplicável: os documentos de identificação e, se
casados, as certidões de casamento dos comparecentes; a certidão atualizada da
matrícula e de ônus reais, expedida em [DATA DA CERTIDÃO DA MATRÍCULA]; o
comprovante do ITBI; o CCIR; e o comprovante do ITR. «SE CAR: o comprovante de
inscrição no CAR.» «SE HOUVE CONSULTA À CNIB: Procedeu-se à consulta prévia à
Central Nacional de Indisponibilidade de Bens sobre o OUTORGANTE VENDEDOR, sob
o protocolo/hash [PROTOCOLO OU HASH DA CONSULTA À CNIB], nada constando em
desfavor.» Quanto às certidões judiciais e administrativas não legalmente
indispensáveis, o OUTORGADO COMPRADOR declara ter sido informado acerca de sua
possibilidade e DISPENSA EXPRESSAMENTE SUA APRESENTAÇÃO, ASSUMINDO OS RISCOS
DECORRENTES DA DISPENSA. XI - DA PUBLICIDADE, DA DOI, DA LGPD E DA PREVENÇÃO À
LAVAGEM DE DINHEIRO: Fica consignado que será emitida a Declaração sobre
Operação Imobiliária (DOI), nos termos do artigo 8º da Lei n. 10.426, de 2002,
e do artigo 797 do Código de Normas. Os comparecentes declaram ciência de que
seus dados pessoais serão tratados na medida necessária ao cumprimento das
atribuições legais e regulamentares da atividade notarial e registral,
inclusive para qualificação, lavratura, arquivamento, emissão de selos,
comunicações obrigatórias, fiscalização e registro, na forma da Lei n.
13.709/2018. Foram observadas as normas de prevenção à lavagem de dinheiro e
ao financiamento do terrorismo, tendo as partes sido advertidas de que
respondem pela exatidão das declarações acerca de preço, forma de pagamento,
origem dos recursos, beneficiários e demais informações prestadas. XII - DA
BASE LEGAL, DA LEITURA E DO CONSENTIMENTO: A presente escritura é lavrada com
fundamento nos artigos 108, 215, 481 e seguintes e 1.245 do Código Civil, na
Lei n. 6.015/1973, na Lei n. 7.433/1985 e no Decreto n. 93.240/1986, na Lei n.
4.947/1966, na Lei n. 9.393/1996, no Decreto n. 4.449/2002, no Código Nacional
de Normas do Foro Extrajudicial, instituído pelo Provimento CNJ n. 149/2023 e
suas alterações, e no Código de Normas do Foro Extrajudicial do Maranhão.
XIII - DOS EMOLUMENTOS: «SE SEM LAUDO DE AVALIAÇÃO MUNICIPAL: Para fins de
cobrança dos emolumentos relativos à presente escritura, foi realizado
orçamento com base no valor de referência constante da tabela do INCRA
vigente, considerando-se o valor de [VALOR DE REFERÊNCIA POR HECTARE] por
hectare, resultando no valor total de referência de
[VALOR TOTAL DE REFERÊNCIA], sobre o qual foram calculados os emolumentos e
demais acréscimos legais pertinentes ao ato, conforme tabela de emolumentos
vigente.» Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-DOACAO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de doação",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram: como
OUTORGANTE DOADOR, {{ outorgantes }}; e como OUTORGADO DONATÁRIO,
{{ outorgados }}; reconhecidos como os próprios por mim, tabelião, à vista dos
documentos apresentados, do que dou fé. E, pelo OUTORGANTE DOADOR, me foi dito
que é senhor e legítimo possuidor do imóvel a seguir descrito:
[DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA], havido conforme registro n.
[NÚMERO DO REGISTRO ANTERIOR] da matrícula n. [MATRÍCULA] do
[CARTÓRIO DE REGISTRO DE IMÓVEIS]. E que, por este instrumento e na melhor
forma de direito, doa o referido imóvel ao OUTORGADO DONATÁRIO, a título
gratuito e por liberalidade, atribuindo ao bem doado o valor de
[VALOR ATRIBUÍDO POR EXTENSO] ([VALOR ATRIBUÍDO EM ALGARISMOS]).
«SE ADIANTAMENTO DE LEGÍTIMA: A presente doação é feita ao descendente a título
de adiantamento da legítima, e deverá ser conferida no inventário do doador, na
forma dos artigos 544 e 2.002 do Código Civil.» «SE DISPENSA DE COLAÇÃO: O
doador dispensa expressamente a colação, saindo a doação da parte disponível de
seu patrimônio, na forma dos artigos 2.005 e 2.006 do Código Civil.»
«SE RESERVA DE USUFRUTO: A doação é feita com reserva de usufruto vitalício em
favor do OUTORGANTE DOADOR, ficando com o OUTORGADO DONATÁRIO a nua
propriedade, usufruto que será objeto de registro próprio.» «SE CLÁUSULAS
RESTRITIVAS: Grava o doador o imóvel doado com as cláusulas de
INALIENABILIDADE, IMPENHORABILIDADE e INCOMUNICABILIDADE vitalícias, pela
seguinte justa causa, que declara nos termos do artigo 1.848 do Código Civil:
[JUSTA CAUSA DAS CLÁUSULAS RESTRITIVAS].» «SE REVERSÃO: Estipula o doador a
cláusula de reversão, de modo que o imóvel doado retorne ao seu patrimônio se
sobreviver ao OUTORGADO DONATÁRIO, na forma do artigo 547 do Código Civil.»
Declara o OUTORGANTE DOADOR que a presente liberalidade não excede a parte de
que poderia dispor em testamento e que lhe restam bens e renda suficientes para
a própria subsistência, na forma dos artigos 548 e 549 do Código Civil. Pelo
OUTORGADO DONATÁRIO me foi dito que ACEITA a presente doação em todos os seus
termos e condições. Foram-me apresentados e ficam arquivados: a certidão
atualizada da matrícula, expedida em [DATA DA CERTIDÃO DA MATRÍCULA]; e o
comprovante de recolhimento do ITCMD, guia n. [NÚMERO DA GUIA DE ITCMD],
recolhida em [DATA DO ITCMD]. Fica consignado que será emitida a Declaração
sobre Operação Imobiliária (DOI). Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    # =================================================== PROCURAÇÕES

    {
        "codigo": "NT-PROC-PUBLICA",
        "tipo": "PROCURACAO",
        "nome": "Procuração pública",
        "natureza": "Procuração",
        "tipo_ato_cep": 2,
        "fundamentacao": ("CC, arts. 653 a 692, com destaque para o art. 661, "
                          "§ 1º; CN/TJMA, arts. 831 a 833"),
        "requisitos": COMUNS_PROCURACAO,
        "corpo": _corpo("""<p>Saibam quantos este público instrumento virem
que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como
OUTORGANTE {{ outorgantes }}, reconhecido como o próprio por mim, tabelião, à
vista dos documentos apresentados, do que dou fé. E, pelo OUTORGANTE, me foi
dito que, por este instrumento, nomeia e constitui seu bastante procurador
{{ outorgados }}, a quem confere os poderes de [DESCRIÇÃO DOS PODERES
CONFERIDOS, DE FORMA CLARA E PRECISA], podendo para tanto assinar os documentos
necessários, prestar declarações, requerer e retirar certidões, pagar e receber
quitação, e praticar todos os demais atos necessários ao fiel cumprimento deste
mandato. «SE PODERES ESPECIAIS: Confere ainda o OUTORGANTE, de forma expressa e
na dicção do artigo 661, § 1º, do Código Civil, os poderes especiais de
[PODERES ESPECIAIS: ALIENAR, GRAVAR, TRANSIGIR, RENUNCIAR, DAR QUITAÇÃO OU
RECEBER CITAÇÃO], que não se presumem e que somente valem porque aqui
declarados.» «SE PODERES SOBRE IMÓVEL: Os poderes ora conferidos alcançam o
imóvel objeto da matrícula n. [MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS],
tendo sido exigida e arquivada nesta serventia a certidão atualizada do registro
de imóveis, expedida em [DATA DA CERTIDÃO DO REGISTRO DE IMÓVEIS], na forma do
artigo 833 do Código de Normas.» «SE SUBSTABELECIMENTO PERMITIDO: Poderá o
procurador substabelecer este mandato, com ou sem reserva de poderes.»
«SE SUBSTABELECIMENTO VEDADO: É vedado ao procurador substabelecer este
mandato.» «SE CAUSA PRÓPRIA: O presente mandato é outorgado EM CAUSA PRÓPRIA,
na forma do artigo 685 do Código Civil, sendo irrevogável e não se extinguindo
pela morte de qualquer das partes.» {PRAZO: O presente mandato vigorará por
prazo indeterminado | O presente mandato terá validade até
[DATA DE VALIDADE DA PROCURAÇÃO], extinguindo-se de pleno direito nessa data}.
Nada mais. O presente instrumento de procuração foi lido e achado conforme em
todos os seus termos por todos comparecentes. Emolumentos e selo de
fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM
QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após
redigir, subscrever, assino em público e raso, encerrando o presente ato.
Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-PROC-CAUSA-PROPRIA",
        "tipo": "PROCURACAO",
        "nome": "Procuração em causa própria",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como
OUTORGANTE {{ outorgantes }}, reconhecido como o próprio por mim, tabelião, do
que dou fé. E, pelo OUTORGANTE, me foi dito que, por este instrumento, nomeia e
constitui seu bastante procurador EM CAUSA PRÓPRIA {{ outorgados }}, na forma
do artigo 685 do Código Civil, transferindo-lhe todos os direitos que detém
sobre [OBJETO DA PROCURAÇÃO EM CAUSA PRÓPRIA], para que o exerça em seu próprio
nome e proveito, podendo dispor do bem ou direito como lhe convier,
independentemente de prestação de contas. «SE OPERAÇÃO ONEROSA: A presente
outorga é feita a título oneroso, pelo preço certo e ajustado de
[PREÇO POR EXTENSO] ([PREÇO EM ALGARISMOS]), já recebido pelo OUTORGANTE, que
dá plena, geral e irrevogável quitação, regendo-se o negócio pelas normas da
compra e venda, na forma do artigo 481 e seguintes do Código Civil e do artigo
834, parágrafo único, do Código de Normas.» Declara o OUTORGANTE estar ciente
de que o presente mandato é IRREVOGÁVEL, não se extingue pela sua morte nem
pela do procurador, e dispensa a prestação de contas, na forma do artigo 685 do
Código Civil. Nada mais. O presente instrumento de procuração foi lido e achado
conforme em todos os seus termos por todos comparecentes. Emolumentos e selo
de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO
EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e
após redigir, subscrever, assino em público e raso, encerrando o presente ato.
Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-SUBSTABELECIMENTO",
        "tipo": "SUBSTABELECIMENTO",
        "nome": "Substabelecimento de mandato",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como
SUBSTABELECENTE {{ outorgantes }}, reconhecido como o próprio por mim,
tabelião, do que dou fé. E, pelo SUBSTABELECENTE, me foi dito que é procurador
de [NOME DO MANDANTE ORIGINÁRIO], conforme procuração lavrada em
[DATA DA PROCURAÇÃO ORIGINÁRIA], no Livro [LIVRO DA PROCURAÇÃO ORIGINÁRIA],
folhas [FOLHAS DA PROCURAÇÃO ORIGINÁRIA], do [SERVENTIA DA PROCURAÇÃO
ORIGINÁRIA], inscrita sob o CNS [CNS DA SERVENTIA DE ORIGEM], e que, por este
instrumento, SUBSTABELECE {RESERVA: COM reserva de iguais poderes, continuando
a exercê-los | SEM reserva de poderes, deles se afastando integralmente} os
poderes que lhe foram conferidos, em favor de {{ outorgados }}, para que os
exerça nos exatos limites do mandato originário, [PODERES SUBSTABELECIDOS].
Declara o SUBSTABELECENTE que o mandato originário está em pleno vigor, que não
foi revogado nem renunciado, e que os poderes ora substabelecidos não excedem
os que lhe foram outorgados. «SE VEDAÇÃO DE NOVO SUBSTABELECIMENTO: É vedado ao
substabelecido substabelecer, no todo ou em parte, os poderes ora recebidos.»
Fica ciente o SUBSTABELECENTE de que, no substabelecimento sem reserva,
responde perante o mandante pelos prejuízos ocorridos sob a gerência do
substabelecido se agiu com culpa na escolha deste ou nas instruções dadas, na
forma do artigo 667, § 4º, do Código Civil. Nada mais. O presente
substabelecimento foi lido e achado conforme em todos os seus termos por todos
comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o
ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos
constatados e dos documentos apresentados e após redigir, subscrever, assino em
público e raso, encerrando o presente ato. Traslado emitido e entregue às
partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-REVOGACAO-MANDATO",
        "tipo": "REVOGACAO_PROCURACAO",
        "nome": "Revogação de mandato",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento virem
que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como
OUTORGANTE {{ outorgantes }}, reconhecido como o próprio por mim, tabelião, do
que dou fé. E, pelo OUTORGANTE, me foi dito que, por instrumento público lavrado
em [DATA DA PROCURAÇÃO REVOGADA], no Livro [LIVRO DA PROCURAÇÃO REVOGADA],
folhas [FOLHAS DA PROCURAÇÃO REVOGADA], do [SERVENTIA DA PROCURAÇÃO REVOGADA],
inscrita sob o CNS [CNS DA SERVENTIA DE ORIGEM], constituiu bastante procurador
{{ outorgados }}, e que, por este instrumento e na melhor forma de direito,
REVOGA integralmente aquele mandato, tornando-o sem efeito a partir desta data,
para que dele não se use mais, cessando todos os poderes ali conferidos, na
forma do artigo 682, I, do Código Civil. Fica o OUTORGANTE expressamente
advertido por mim, tabelião, na forma do artigo 831, § 2º, do Código de Normas,
de que é IMPRESCINDÍVEL notificar o mandatário desta revogação, e de que a
revogação só produz efeito perante terceiros de boa-fé depois de conhecida, nos
termos do artigo 686 do Código Civil, respondendo por perdas e danos na hipótese
de mandato com cláusula de irrevogabilidade, conforme o artigo 683 do mesmo
diploma. «SE MANDATÁRIO PRESENTE: Presente ao ato o mandatário, dá-se por
notificado da revogação neste ato e devolve o instrumento de mandato, que fica
arquivado nesta serventia.» «SE LAVRADO NESTA SERVENTIA: Procedi, nesta data, à
anotação da presente revogação à margem do ato originário, sem qualquer ônus
para as partes e sem aposição de selo, na forma do artigo 831 do Código de
Normas.» «SE LAVRADO EM OUTRA SERVENTIA: Será comunicada a presente revogação ao
tabelionato que lavrou o mandato, por meio que comprove o recebimento, mediante
o pagamento da despesa postal pelo interessado, na forma do artigo 831, § 1º, do
Código de Normas.» Nada mais. O presente instrumento de revogação foi lido e
achado conforme em todos os seus termos por todos comparecentes. Emolumentos e
selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A
CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos
apresentados e após redigir, subscrever, assino em público e raso, encerrando o
presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-RENUNCIA-MANDATO",
        "tipo": "RENUNCIA_PROCURACAO",
        "nome": "Renúncia de mandato",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento virem
que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como
RENUNCIANTE {{ outorgantes }}, reconhecido como o próprio por mim, tabelião, do
que dou fé. E, pelo RENUNCIANTE, me foi dito que é procurador de
[NOME DO MANDANTE], conforme instrumento público lavrado em
[DATA DA PROCURAÇÃO RENUNCIADA], no Livro [LIVRO DA PROCURAÇÃO RENUNCIADA],
folhas [FOLHAS DA PROCURAÇÃO RENUNCIADA], do [SERVENTIA DA PROCURAÇÃO
RENUNCIADA], inscrita sob o CNS [CNS DA SERVENTIA DE ORIGEM], e que, por este
instrumento e na melhor forma de direito, RENUNCIA aos poderes que lhe foram
conferidos, deles se afastando integralmente a partir desta data, na forma do
artigo 682, I, do Código Civil. Fica o RENUNCIANTE expressamente advertido por
mim, tabelião, de que deve comunicar a renúncia ao mandante, e de que, sendo a
renúncia intempestiva e ausente motivo legítimo, responde pelos prejuízos
causados, salvo se provar que não podia continuar no mandato sem prejuízo
considerável, na forma do artigo 688 do Código Civil. «SE LAVRADO NESTA
SERVENTIA: Procedi, nesta data, à anotação da presente renúncia à margem do ato
originário, sem qualquer ônus para as partes e sem aposição de selo, na forma do
artigo 831 do Código de Normas.» «SE LAVRADO EM OUTRA SERVENTIA: Será comunicada
a presente renúncia ao tabelionato que lavrou o mandato, por meio que comprove o
recebimento, na forma do artigo 831, § 1º, do Código de Normas.» Nada mais. O
presente instrumento de renúncia foi lido e achado conforme em todos os seus
termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do
ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos
fatos constatados e dos documentos apresentados e após redigir, subscrever,
assino em público e raso, encerrando o presente ato. Traslado emitido e
entregue às partes após as assinaturas.</p>
"""),
    },

    # =================================================== ATAS NOTARIAIS

    {
        "codigo": "NT-ATA-NOTARIAL",
        "tipo": "ATA_NOTARIAL",
        "nome": "Ata notarial",
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
        "corpo": _corpo("""<p>Saibam quantos esta ata notarial virem que, aos
[DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano
de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), às [HORA POR EXTENSO]
([HORA EM ALGARISMOS]) horas, nesta cidade de {{ sv.ri_cidade }}, Estado do
{{ sv.ri_uf }}, {LUGAR DA LAVRATURA: nesta serventia | no local situado em [ENDEREÇO DA DILIGÊNCIA], onde me desloquei a pedido do solicitante, dentro dos limites da circunscrição desta delegação | em meio eletrônico, acessado a partir desta serventia}, perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }},
compareceu como SOLICITANTE {{ outorgantes }}, reconhecido como o próprio por
mim, tabelião, à vista dos documentos apresentados, do que dou fé. E, pelo
SOLICITANTE, me foi requerido que eu constatasse e reduzisse a termo os fatos a
seguir narrados, ao que atendi, passando a narrar objetivamente o que percebi
com os meus próprios sentidos, sem emitir juízo de valor sobre o que constatei:
[NARRAÇÃO CIRCUNSTANCIADA DOS FATOS, EM ORDEM CRONOLÓGICA, COM O QUE FOI VISTO,
OUVIDO E CONSTATADO]. «SE HOUVER DOCUMENTO: O SOLICITANTE apresentou-me o
documento a seguir identificado, cujo teor transcrevo integralmente, na forma do
artigo 847, § 4º, do Código de Normas: [TEOR INTEGRAL DO DOCUMENTO].»
«SE HOUVER ANEXO: Ficam anexados a esta ata, numerados sequencialmente e
arquivados em pasta própria, os seguintes documentos: [RELAÇÃO DOS DOCUMENTOS
ANEXADOS].» «SE HOUVER TESTEMUNHA: Presentes ao ato, como testemunhas,
{{ testemunhas }}, que presenciaram os fatos ora narrados.» Nada mais havendo a
constatar, encerro a presente ata às [HORA DO ENCERRAMENTO POR EXTENSO]
([HORA DO ENCERRAMENTO EM ALGARISMOS]) horas. Esta ata foi por mim lida em voz
alta ao SOLICITANTE «SE HOUVER TESTEMUNHA: e às testemunhas», que a acharam
conforme e a assinam, do que dou fé.</p>
"""),
    },

    {
        "codigo": "NT-ATA-USUCAPIAO",
        "tipo": "ATA_USUCAPIAO",
        "nome": "Ata notarial para usucapião extrajudicial",
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
        "corpo": _corpo("""<p>Saibam quantos
esta ata notarial virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do
mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), às
[HORA POR EXTENSO] ([HORA EM ALGARISMOS]) horas, nesta cidade de
{{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante mim,
{{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como REQUERENTE
{{ outorgantes }}, reconhecido como o próprio por mim, tabelião, do que dou fé.
E, pelo REQUERENTE, me foi requerida a lavratura de ata notarial para fins de
reconhecimento extrajudicial de usucapião, na modalidade
{MODALIDADE: ordinária, do artigo 1.242 do Código Civil | extraordinária, do
artigo 1.238 do Código Civil | especial rural, do artigo 191 da Constituição
Federal | especial urbana, do artigo 183 da Constituição Federal | especial
familiar, do artigo 1.240-A do Código Civil}, relativamente ao imóvel assim
descrito e caracterizado: [DESCRIÇÃO DO IMÓVEL CONFORME PLANTA E MEMORIAL
DESCRITIVO], «SE HOUVER MATRÍCULA: objeto da matrícula n. [MATRÍCULA] do
[CARTÓRIO DE REGISTRO DE IMÓVEIS]», «SE NÃO HOUVER MATRÍCULA: sem matrícula
aberta no Registro de Imóveis competente», confrontando com
[NOMES E QUALIFICAÇÃO DOS CONFRONTANTES]. Passo a ATESTAR, com base nos
documentos que me foram apresentados e nas declarações que colhi, o tempo de
posse do REQUERENTE e de seus antecessores, na forma do artigo 846, parágrafo
único, V, do Código de Normas: o REQUERENTE exerce posse sobre o imóvel desde
[DATA DE INÍCIO DA POSSE DO REQUERENTE], de forma mansa, pacífica e
ininterrupta, e sem oposição de quem quer que seja. «SE HOUVER ACESSÃO DE POSSE:
Soma o REQUERENTE à sua a posse de seus antecessores, a saber:
[NOMES DOS ANTECESSORES, PERÍODOS E FORMA DE TRANSMISSÃO DA POSSE], perfazendo
o tempo total de [TEMPO TOTAL DE POSSE POR EXTENSO] ([TEMPO TOTAL DE POSSE EM
ALGARISMOS]) anos, na forma do artigo 1.243 do Código Civil.» A posse assim
atestada assenta-se nos seguintes elementos, que me foram apresentados e ficam
arquivados: [RELAÇÃO DOS DOCUMENTOS QUE DEMONSTRAM A ORIGEM, A CONTINUIDADE E O
TEMPO DA POSSE]. «SE HOUVER TESTEMUNHA: Presentes ao ato, como testemunhas,
{{ testemunhas }}, que declararam conhecer o imóvel e confirmar o tempo de posse
ora atestado.» Declara o REQUERENTE, sob as penas da lei, que não possui outro
imóvel «SE ESPECIAL: urbano ou rural», e que a posse ora descrita nunca foi
objeto de oposição judicial ou extrajudicial. CONSIGNO EXPRESSAMENTE que a
presente ata notarial ATESTA O TEMPO DE POSSE, e não declara a propriedade nem
reconhece a usucapião, cabendo ao Oficial de Registro de Imóveis competente a
análise do pedido e a decisão sobre o registro, na forma do artigo 216-A da Lei
n. 6.015, de 1973. Encerro a presente ata às [HORA DO ENCERRAMENTO POR EXTENSO]
([HORA DO ENCERRAMENTO EM ALGARISMOS]) horas, que foi por mim lida em voz alta
ao REQUERENTE, que a achou conforme e a assina, do que dou fé.</p>
"""),
    },

    {
        "codigo": "NT-ATA-ADJUDICACAO",
        "tipo": "ATA_NOTARIAL",
        "nome": "Ata notarial para adjudicação compulsória extrajudicial",
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
        "corpo": _corpo("""<p>Saibam quantos esta ata notarial virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), às [HORA POR EXTENSO]
([HORA EM ALGARISMOS]) horas, nesta cidade de {{ sv.ri_cidade }}, Estado do
{{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceu como REQUERENTE {{ outorgantes }}, na
qualidade de {QUALIDADE: promitente comprador | cessionário}, reconhecido como
o próprio por mim, tabelião, do que dou fé. E, pelo REQUERENTE, me foi
requerida a lavratura de ata notarial para fins de adjudicação compulsória
extrajudicial, na forma do artigo 216-B da Lei n. 6.015, de 1973, e do artigo
848 do Código de Normas, relativamente ao imóvel objeto da matrícula n.
[MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS], com inscrição cadastral n.
[INSCRIÇÃO CADASTRAL], assim descrito: [DESCRIÇÃO DO IMÓVEL CONFORME A
MATRÍCULA]. Foram-me apresentados e ficam arquivados nesta serventia, e passo a
ATESTAR o que deles consta: o {TÍTULO: contrato de promessa de compra e venda |
instrumento de cessão de direitos} celebrado em [DATA DO CONTRATO] entre
[NOME DO PROMITENTE VENDEDOR] e o REQUERENTE, tendo por objeto o imóvel acima
descrito; a prova da QUITAÇÃO integral do preço, consistente em
[PROVA DA QUITAÇÃO]; a prova da NOTIFICAÇÃO do promitente vendedor para outorga
da escritura definitiva, realizada em [DATA DA NOTIFICAÇÃO] por
[FORMA DA NOTIFICAÇÃO], e a prova de sua INÉRCIA, decorrido o prazo de
[PRAZO DA NOTIFICAÇÃO] sem que a escritura fosse outorgada; e a certidão de
INEXISTÊNCIA DE LITÍGIO judicial ou arbitral envolvendo o contrato ou o imóvel,
expedida em [DATA DA CERTIDÃO DE INEXISTÊNCIA DE LITÍGIO]. Foi ainda
apresentado o comprovante de recolhimento do ITBI, guia n.
[NÚMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI]. Diante do exposto,
ATESTO o preenchimento dos requisitos legais para a adjudicação compulsória
extrajudicial, servindo a presente ata como título hábil para ingresso no
Registro de Imóveis competente, independentemente de homologação judicial, na
forma do artigo 848, § 2º, do Código de Normas, ressalvada ao Oficial de
Registro de Imóveis a qualificação do título, que lhe é privativa. Encerro a
presente ata às [HORA DO ENCERRAMENTO POR EXTENSO]
([HORA DO ENCERRAMENTO EM ALGARISMOS]) horas, que foi por mim lida em voz alta
ao REQUERENTE, que a achou conforme e a assina, do que dou fé.</p>
"""),
    },

    # =================================================== TESTAMENTO

    {
        "codigo": "NT-TESTAMENTO-PUBLICO",
        "tipo": "TESTAMENTO",
        "nome": "Testamento público",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento de
testamento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), às
[HORA POR EXTENSO] ([HORA EM ALGARISMOS]) horas, nesta cidade de
{{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, {LUGAR: nesta serventia | no
endereço [ENDEREÇO DA LAVRATURA], para onde me desloquei a pedido do testador},
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como TESTADOR
{{ outorgantes }}, reconhecido como o próprio por mim, tabelião, à vista dos
documentos apresentados, do que dou fé; e, presentes ao ato desde o seu início e
até o seu encerramento, as testemunhas instrumentárias {{ testemunhas }}, todas
capazes, conhecidas de mim, tabelião, e não incidentes em nenhum dos
impedimentos dos artigos 228 e 1.801 do Código Civil. DOU FÉ de que o TESTADOR
se encontra em pleno gozo de suas faculdades mentais, orientado no tempo e no
espaço, exprimindo sua vontade de forma livre, consciente e desembaraçada, sem
qualquer sinal de coação, indução ou vício de vontade, e de que declarou fazê-lo
de livre e espontânea vontade. E, pelo TESTADOR, na presença das testemunhas, me
foram feitas as declarações que passo a escrever, na forma do artigo 1.864, I,
do Código Civil: PRIMEIRO, declara chamar-se como acima qualificado e ser
{ESTADO CIVIL DO TESTADOR: solteiro | casado | divorciado | viúvo | separado
judicialmente | convivente em união estável}, «SE CASADO OU CONVIVENTE: sendo
seu {CÔNJUGE OU CONVIVENTE: cônjuge | convivente} [NOME E QUALIFICAÇÃO DO
CÔNJUGE OU CONVIVENTE], sob o regime de [REGIME DE BENS]». SEGUNDO, declara
{FILHOS: não possuir filhos nem outros descendentes | possuir os seguintes
filhos: [NOMES E QUALIFICAÇÃO DOS FILHOS]}, e {ASCENDENTES: não possuir
ascendentes vivos | possuir os seguintes ascendentes vivos: [NOMES E
QUALIFICAÇÃO DOS ASCENDENTES]}. TERCEIRO, declara que, tendo conhecimento de que
a legítima dos herdeiros necessários corresponde à metade dos bens da herança e
não pode ser objeto de disposição testamentária, na forma dos artigos 1.789,
1.846 e 1.857, § 1º, do Código Civil, dispõe pelo presente testamento
[OBJETO DA DISPOSIÇÃO: DA PARTE DISPONÍVEL OU DA TOTALIDADE DOS BENS, CONFORME O
CASO], nos seguintes termos: [DISPOSIÇÕES TESTAMENTÁRIAS, COM A IDENTIFICAÇÃO DE
CADA HERDEIRO OU LEGATÁRIO E DE CADA BEM OU QUOTA ATRIBUÍDA].
«SE HOUVER LEGADO: QUARTO, institui os seguintes legados: [DESCRIÇÃO DOS BENS
LEGADOS E IDENTIFICAÇÃO DOS LEGATÁRIOS].» «SE HOUVER CLÁUSULAS RESTRITIVAS:
Grava os bens ora deixados com as cláusulas de INALIENABILIDADE,
IMPENHORABILIDADE e INCOMUNICABILIDADE, declarando, para tanto e como exige o
artigo 1.848 do Código Civil, a seguinte JUSTA CAUSA: [JUSTA CAUSA DAS CLÁUSULAS
RESTRITIVAS].» «SE HOUVER SUBSTITUIÇÃO: Institui substituição, de modo que, não
podendo ou não querendo aceitar o herdeiro ou legatário instituído, a ele se
substitua [NOME E QUALIFICAÇÃO DO SUBSTITUTO], na forma dos artigos 1.947 e
seguintes do Código Civil.» «SE HOUVER DESERDAÇÃO: Deserda o herdeiro necessário
[NOME E QUALIFICAÇÃO DO DESERDADO], declarando expressamente a seguinte causa,
como exigem os artigos 1.964 e 1.965 do Código Civil: [CAUSA DA DESERDAÇÃO].»
«SE HOUVER TESTAMENTEIRO: Nomeia testamenteiro [NOME E QUALIFICAÇÃO DO
TESTAMENTEIRO], a quem confere a posse e a administração da herança, e arbitra
prêmio de [PRÊMIO DO TESTAMENTEIRO], na forma dos artigos 1.976 e seguintes do
Código Civil.» «SE HOUVER RECONHECIMENTO DE FILHO: Reconhece como seu filho
[NOME E QUALIFICAÇÃO DO FILHO RECONHECIDO], reconhecimento que é irrevogável e
não perde eficácia ainda que o testamento venha a caducar por outra causa, na
forma dos artigos 1.609, III, e 1.610 do Código Civil.» «SE REVOGAÇÃO DE
TESTAMENTO ANTERIOR: REVOGA o TESTADOR, expressamente, o testamento anterior
lavrado em [DATA DO TESTAMENTO REVOGADO], no Livro [LIVRO DO TESTAMENTO
REVOGADO], folhas [FOLHAS DO TESTAMENTO REVOGADO], do [SERVENTIA DO TESTAMENTO
REVOGADO], inscrita sob o CNS [CNS DA SERVENTIA DO TESTAMENTO REVOGADO], na
forma do artigo 1.969 do Código Civil.» Assim o disse e assim eu escrevi, de
acordo com as suas declarações. E, LAVRADO O INSTRUMENTO, EU O LI EM VOZ ALTA AO
TESTADOR E ÀS DUAS TESTEMUNHAS, A UM SÓ TEMPO, na presença simultânea de todos,
na forma do artigo 1.864, II, do Código Civil, tendo o TESTADOR declarado que o
instrumento exprime fielmente a sua última vontade. «SE TESTADOR CEGO: Por ser o
TESTADOR cego, este testamento lhe foi lido EM VOZ ALTA DUAS VEZES: a primeira
por mim, tabelião, e a segunda pela testemunha [NOME DA TESTEMUNHA DESIGNADA
PELO TESTADOR], por ele designada para esse fim, de tudo se fazendo esta
circunstanciada menção, na forma do artigo 1.867 do Código Civil.»
«SE TESTADOR SURDO QUE SABE LER: Por ser o TESTADOR surdo e saber ler, ele
próprio leu este testamento, na presença das testemunhas e de mim, tabelião, na
forma do artigo 1.866 do Código Civil.» «SE TESTADOR SURDO QUE NÃO SABE LER: Por
ser o TESTADOR surdo e não saber ler, designou [NOME DE QUEM LEU EM SEU LUGAR]
para ler este testamento em seu lugar, o que foi feito na presença das
testemunhas, na forma do artigo 1.866 do Código Civil.» Em seguida à leitura, e
achado conforme, assinam o TESTADOR, as duas testemunhas e eu, tabelião, na
forma do artigo 1.864, III, do Código Civil. «SE TESTADOR NÃO ASSINA: Declaro
que o TESTADOR não [MOTIVO: sabe | pode] assinar, motivo pelo qual assina a seu
rogo a testemunha instrumentária [NOME DA TESTEMUNHA QUE ASSINA A ROGO], na
forma do artigo 1.865 do Código Civil, colhendo-se ainda a impressão digital do
TESTADOR.» Encerro este testamento às [HORA DO ENCERRAMENTO POR EXTENSO]
([HORA DO ENCERRAMENTO EM ALGARISMOS]) horas, do que dou fé.</p>
"""),
    },

    # =================================================== SUCESSÕES

    {
        "codigo": "NT-ESC-CESSAO-HEREDITARIA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de cessão de direitos hereditários",
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
        "corpo": _corpo("""<p>Saibam quantos
este público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS])
dias do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO]
([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }}, Estado do
{{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram: como CEDENTE, {{ outorgantes }}; e como
CESSIONÁRIO, {{ outorgados }}; reconhecidos como os próprios por mim, tabelião,
à vista dos documentos apresentados, do que dou fé. E, pelo CEDENTE, me foi dito
que é herdeiro de [NOME DO AUTOR DA HERANÇA], falecido em
[DATA DO ÓBITO DO AUTOR DA HERANÇA], na cidade de [LUGAR DO ÓBITO], conforme
certidão de óbito lavrada sob o termo n. [TERMO DO ÓBITO], no Livro
[LIVRO DO ÓBITO], folhas [FOLHAS DO ÓBITO], do [SERVENTIA DO REGISTRO DO ÓBITO],
e que, na qualidade de [QUALIDADE DO CEDENTE NA SUCESSÃO], lhe cabe o quinhão
hereditário correspondente a [FRAÇÃO DO QUINHÃO EM FRAÇÃO DECIMAL OU ORDINÁRIA]
do acervo. E que, por este instrumento e na melhor forma de direito, CEDE E
TRANSFERE ao CESSIONÁRIO a totalidade dos direitos hereditários que lhe cabem
naquela sucessão, {ONEROSIDADE: a título oneroso, pelo preço certo e ajustado de
[PREÇO POR EXTENSO] ([PREÇO EM ALGARISMOS]), já recebido, do que dá plena,
geral e irrevogável quitação | a título gratuito, por mera liberalidade}.
CIENTIFICO EXPRESSAMENTE o CESSIONÁRIO, na forma do artigo 803 do Código de
Normas, e ele declara estar ciente, de que a presente cessão compreende não só o
quinhão ou a quota ideal atribuível ao CEDENTE nos bens, MAS TAMBÉM,
PROPORCIONALMENTE, AS DÍVIDAS DO ESPÓLIO, até o limite das forças da herança.
Declara o CEDENTE que deu ciência aos demais coerdeiros da presente cessão, com
especificação do valor, da forma de pagamento e das demais condições ora
ajustadas, para os fins do direito de preferência do artigo 1.795 do Código
Civil, ciência comprovada por [FORMA DA CIÊNCIA AOS COERDEIROS]. «SE COERDEIROS
PRESENTES: Presentes ao ato os demais coerdeiros, {{ testemunhas }}, que
declaram estar cientes da cessão e RENUNCIAR expressamente ao direito de
preferência que lhes assiste.» «SE OUTORGA UXÓRIA: Comparece ainda ao ato, para
dar a competente outorga, o cônjuge do CEDENTE, [NOME E QUALIFICAÇÃO DO CÔNJUGE
DO CEDENTE], que anui à presente cessão em todos os seus termos, na forma do
artigo 1.647, I, do Código Civil.» «SE DISPENSA DE OUTORGA: Fica dispensada a
outorga do cônjuge, por ser o regime de bens o de [REGIME QUE DISPENSA A
OUTORGA], na forma do artigo 1.647, caput, do Código Civil e do artigo 804,
§ 4º, do Código de Normas.» «SE BEM INDIVIDUALIZADO: A presente cessão recai
sobre bem individualizado da herança, a saber: [DESCRIÇÃO DO BEM
INDIVIDUALIZADO], correspondendo ao quinhão ideal de [QUINHÃO IDEAL EM FRAÇÃO
DECIMAL OU ORDINÁRIA]. FICAM AS PARTES CIENTES, na forma do artigo 805 do Código
de Normas, de que este título NÃO É HÁBIL para ingresso no Registro de Imóveis
até que seja feita a partilha.» Foram-me apresentados e ficam arquivados: a
certidão de óbito do autor da herança; e o comprovante de recolhimento do
imposto de transmissão, guia n. [NÚMERO DA GUIA DO IMPOSTO], recolhida em
[DATA DO IMPOSTO]. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-INVENTARIO-PARTILHA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de inventário e partilha",
        "natureza": "Inventário e partilha",
        "tipo_cesdi": 5,
        "fundamentacao": ("CPC, arts. 610 e 733; Lei 11.441/2007; Resolução CNJ "
                          "35/2007, arts. 20 a 25; CN/TJMA, arts. 806 a 813 e 821"),
        "requisitos": COMUNS_SUCESSAO,
        "corpo": _corpo("""<p>Saibam quantos este
público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias
do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]),
nesta cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram as partes a
seguir qualificadas, todas maiores, capazes e concordes: {{ outorgantes }},
reconhecidas como as próprias por mim, tabelião, à vista dos documentos
apresentados, do que dou fé. <b>DO AUTOR DA HERANÇA.</b> Declaram os
comparecentes que a presente escritura tem por objeto a sucessão de
[NOME COMPLETO DO AUTOR DA HERANÇA], [QUALIFICAÇÃO COMPLETA DO AUTOR DA
HERANÇA], que era casado sob o regime de [REGIME DE BENS DO AUTOR DA HERANÇA],
«SE HOUVE PACTO ANTENUPCIAL: conforme pacto antenupcial lavrado em
[DATA DO PACTO ANTENUPCIAL] e registrado sob o n. [REGISTRO DO PACTO
ANTENUPCIAL] no [CARTÓRIO DO REGISTRO DO PACTO]». <b>DO ÓBITO.</b> O autor da
herança faleceu em [DATA DO ÓBITO], na cidade de [LUGAR DO ÓBITO], conforme
certidão de óbito expedida em [DATA DA EXPEDIÇÃO DA CERTIDÃO DE ÓBITO], lavrada
sob o termo n. [TERMO DO ÓBITO], no Livro [LIVRO DO ÓBITO], folhas
[FOLHAS DO ÓBITO], do [SERVENTIA DO REGISTRO DO ÓBITO]. <b>DA INEXISTÊNCIA DE
TESTAMENTO E DE OUTROS HERDEIROS.</b> Declaram os comparecentes, SOB AS PENAS DA
LEI, que o autor da herança não deixou testamento e não deixou outros herdeiros
além dos aqui qualificados, o que se confirma pela certidão negativa expedida
pela CENSEC em [DATA DA CERTIDÃO DA CENSEC], sob o n. [NÚMERO DA CERTIDÃO DA
CENSEC], que fica arquivada nesta serventia. <b>DO CÔNJUGE SUPÉRSTITE.</b>
{CÔNJUGE: Sobrevive ao autor da herança o cônjuge [NOME DO CÔNJUGE SUPÉRSTITE],
a quem cabe a meação sobre os bens comuns | Não há cônjuge supérstite}.
<b>DOS HERDEIROS.</b> São herdeiros do autor da herança
[NOMES E QUALIFICAÇÃO DOS HERDEIROS, COM O VÍNCULO DE PARENTESCO], conforme
certidões comprobatórias apresentadas e arquivadas. <b>DA NOMEAÇÃO DE
INVENTARIANTE.</b> Nomeiam os comparecentes, de comum acordo, para exercer o
encargo de INVENTARIANTE, [NOME DO INVENTARIANTE], que declara aceitá-lo.
<b>DOS ADVOGADOS.</b> Assistem as partes neste ato
[NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB DO ADVOGADO OU ADVOGADOS], que
comparecem e assinam esta escritura, na forma do artigo 808, § 1º, do Código de
Normas. <b>DOS BENS IMÓVEIS.</b> Compõem o acervo os seguintes bens imóveis:
[DESCRIÇÃO DOS IMÓVEIS CONFORME AS MATRÍCULAS, COM VALORES ATRIBUÍDOS].
<b>DOS DIREITOS, AÇÕES E BENS MÓVEIS.</b> Compõem ainda o acervo:
[DESCRIÇÃO DOS BENS MÓVEIS, DIREITOS E AÇÕES, COM VALORES]. <b>DOS
LITÍGIOS.</b> {LITÍGIOS: Declaram os comparecentes não existir litígio judicial
ou extrajudicial sobre os bens ora inventariados | Declaram os comparecentes a
existência do seguinte litígio: [DESCRIÇÃO DO LITÍGIO]}. <b>DAS DÍVIDAS.</b>
{DÍVIDAS: Declaram os comparecentes que o espólio não possui dívidas | Declaram
os comparecentes as seguintes dívidas do espólio: [DESCRIÇÃO DAS DÍVIDAS]}.
<b>DAS RENÚNCIAS E CESSÕES.</b> «SE HOUVER RENÚNCIA OU CESSÃO:
[RENÚNCIAS E CESSÕES, COM A IDENTIFICAÇÃO DE QUEM RENUNCIA OU CEDE E EM FAVOR DE
QUEM].» <b>DA PARTILHA.</b> Os bens são partilhados da seguinte forma:
[PARTILHA, COM O QUINHÃO DE CADA HERDEIRO E OS BENS QUE LHE TOCAM], observada a
meação do cônjuge supérstite, quando houver, e os bens trazidos à colação.
<b>DAS CERTIDÕES E DOCUMENTOS APRESENTADOS.</b> Foram-me apresentados e ficam
arquivados: a certidão de óbito; as certidões de casamento e de vínculo de
parentesco; as certidões de propriedade dos imóveis; as certidões negativas de
tributos das Fazendas Federal, Estadual e Municipal em nome do espólio;
«SE HOUVER IMÓVEL RURAL: o Certificado de Cadastro de Imóvel Rural com a
certidão de quitação do Imposto Territorial Rural;» e a certidão da CENSEC.
<b>DOS IMPOSTOS PAGOS.</b> Foi recolhido o ITCD, guia n.
[NÚMERO DA GUIA DE ITCD], em [DATA DO ITCD], no valor de [VALOR DO ITCD].
<b>DAS DECLARAÇÕES FINAIS.</b> Declaram as partes e os advogados a integral
concordância com os termos desta escritura. «SE HOUVER INCAPAZ: A minuta final
desta escritura foi submetida ao Ministério Público, que se manifestou em
[DATA DO PARECER DO MINISTÉRIO PÚBLICO], e o ato foi aprovado pelo Juízo
competente no procedimento n. [NÚMERO DO PROCEDIMENTO NO PJE], na forma do
artigo 809 do Código de Normas.» «SE HOUVER PROCESSO JUDICIAL: Declaram as
partes estar cientes de que esta escritura somente poderá ser registrada
mediante a comprovação da extinção do processo judicial n.
[NÚMERO DO PROCESSO JUDICIAL], e de que lhes é facultada a suspensão ou a
desistência daquele feito, na forma do artigo 2º da Resolução n. 35 do Conselho
Nacional de Justiça e do artigo 821 do Código de Normas.» Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-SOBREPARTILHA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de sobrepartilha",
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
        "corpo": _corpo("""<p>Saibam quantos este público
instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês
de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram as partes a seguir
qualificadas, todas maiores, capazes e concordes: {{ outorgantes }},
reconhecidas como as próprias por mim, tabelião, do que dou fé. <b>DO AUTOR DA
HERANÇA E DO ÓBITO.</b> Declaram que a presente escritura tem por objeto a
sucessão de [NOME COMPLETO DO AUTOR DA HERANÇA], falecido em [DATA DO ÓBITO], na
cidade de [LUGAR DO ÓBITO], conforme certidão lavrada sob o termo n.
[TERMO DO ÓBITO], no Livro [LIVRO DO ÓBITO], folhas [FOLHAS DO ÓBITO], do
[SERVENTIA DO REGISTRO DO ÓBITO]. <b>DA PARTILHA ANTERIOR.</b> O inventário e a
partilha dos demais bens já foram realizados {PARTILHA ANTERIOR: judicialmente,
nos autos do processo n. [NÚMERO DO PROCESSO DE INVENTÁRIO], que tramitou perante
o [JUÍZO DO INVENTÁRIO], com sentença transitada em julgado em
[DATA DO TRÂNSITO EM JULGADO] | por escritura pública lavrada em
[DATA DA ESCRITURA ANTERIOR], no Livro [LIVRO DA ESCRITURA ANTERIOR], folhas
[FOLHAS DA ESCRITURA ANTERIOR], do [SERVENTIA DA ESCRITURA ANTERIOR]}. <b>DOS
BENS SOBREPARTILHÁVEIS.</b> Declaram os comparecentes que, após aquela partilha,
verificou-se a existência dos seguintes bens, que não foram inventariados nem
partilhados: [DESCRIÇÃO DOS BENS SOBREPARTILHÁVEIS, COM VALORES ATRIBUÍDOS], e
que o motivo de não terem sido partilhados anteriormente foi
[MOTIVO DA SOBREPARTILHA]. <b>DOS HERDEIROS.</b> São herdeiros
[NOMES E QUALIFICAÇÃO DOS HERDEIROS, COM O VÍNCULO DE PARENTESCO].
«SE HERDEIRO ERA INCAPAZ: Consigna-se que [NOME DO HERDEIRO ANTES INCAPAZ] era
menor ou incapaz ao tempo do óbito, sendo hoje maior e plenamente capaz, o que
não impede esta sobrepartilha extrajudicial, na forma do artigo 813 do Código de
Normas e do artigo 25 da Resolução n. 35 do Conselho Nacional de Justiça.»
<b>DOS ADVOGADOS.</b> Assistem as partes [NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB
DO ADVOGADO], que comparece e assina esta escritura. <b>DA SOBREPARTILHA.</b> Os
bens acima descritos são sobrepartilhados da seguinte forma:
[SOBREPARTILHA, COM O QUINHÃO DE CADA HERDEIRO], observada a meação do cônjuge
supérstite, quando houver. <b>DAS CERTIDÕES E DOS IMPOSTOS.</b> Foram
apresentadas e ficam arquivadas as certidões negativas de tributos das Fazendas
Federal, Estadual e Municipal, e a certidão da CENSEC sobre inexistência de
testamento. Foi recolhido o ITCD, guia n. [NÚMERO DA GUIA DE ITCD], em
[DATA DO ITCD]. <b>DAS DECLARAÇÕES FINAIS.</b> Declaram as partes e o advogado a
integral concordância com os termos desta escritura. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-PARTILHA-ADJUDICACAO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de partilha amigável ou adjudicação a herdeiro único",
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
        "corpo": _corpo("""<p>Saibam
quantos este público instrumento virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram as partes a seguir qualificadas, todas
maiores, capazes e concordes: {{ outorgantes }}, reconhecidas como as próprias
por mim, tabelião, do que dou fé. <b>DO AUTOR DA HERANÇA E DO ÓBITO.</b>
Declaram que a presente escritura tem por objeto a sucessão de
[NOME COMPLETO DO AUTOR DA HERANÇA], [QUALIFICAÇÃO COMPLETA DO AUTOR DA
HERANÇA], falecido em [DATA DO ÓBITO], na cidade de [LUGAR DO ÓBITO], conforme
certidão lavrada sob o termo n. [TERMO DO ÓBITO], no Livro [LIVRO DO ÓBITO],
folhas [FOLHAS DO ÓBITO], do [SERVENTIA DO REGISTRO DO ÓBITO]. <b>DA
INEXISTÊNCIA DE TESTAMENTO.</b> Declaram, SOB AS PENAS DA LEI, que o autor da
herança não deixou testamento nem outros herdeiros além dos aqui qualificados,
conforme certidão negativa da CENSEC n. [NÚMERO DA CERTIDÃO DA CENSEC], expedida
em [DATA DA CERTIDÃO DA CENSEC]. <b>DOS HERDEIROS.</b> {HERDEIROS: São herdeiros
[NOMES E QUALIFICAÇÃO DOS HERDEIROS, COM O VÍNCULO DE PARENTESCO] | É herdeiro
único [NOME E QUALIFICAÇÃO DO HERDEIRO ÚNICO], razão pela qual o presente ato é
de ADJUDICAÇÃO, na forma do artigo 814 do Código de Normas}.
«SE DIREITO DE REPRESENTAÇÃO: A sucessão se dá por direito de representação de
[NOME DO REPRESENTADO], falecido em [DATA DO ÓBITO DO REPRESENTADO], conforme
certidão de óbito apresentada e arquivada, na forma do artigo 816 do Código de
Normas.» «SE HOUVER RENÚNCIA: Renuncia à herança [NOME DO RENUNCIANTE], de forma
[MODALIDADE DA RENÚNCIA: ABDICATIVA, EM FAVOR DO MONTE, OU TRANSLATIVA, EM FAVOR
DE HERDEIRO CERTO], renúncia que consta desta escritura, na forma do artigo 815
do Código de Normas.» <b>DOS ADVOGADOS.</b> Assistem as partes
[NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB DO ADVOGADO], que comparece e assina esta
escritura, na forma do artigo 819 do Código de Normas. <b>DOS BENS.</b> Compõem
o acervo os seguintes bens, previamente avaliados:
[DESCRIÇÃO DOS BENS COM OS VALORES DA AVALIAÇÃO]. <b>DA
{ATO: PARTILHA | ADJUDICAÇÃO}.</b> Os bens acima descritos são
{ATO: partilhados da seguinte forma: [PARTILHA, COM O QUINHÃO DE CADA HERDEIRO E
OS BENS QUE LHE TOCAM] | adjudicados integralmente ao herdeiro único acima
qualificado}, observada a meação do cônjuge supérstite, quando houver. <b>DAS
CERTIDÕES E DOS IMPOSTOS.</b> Foram apresentadas e ficam arquivadas as certidões
negativas de tributos das Fazendas Federal, Estadual e Municipal, cujas
informações ficam resumidas neste ato na forma do artigo 817, parágrafo único,
do Código de Normas. Foi recolhido o imposto de transmissão, guia n.
[NÚMERO DA GUIA DO IMPOSTO], em [DATA DO IMPOSTO], no valor de
[VALOR DO IMPOSTO]. <b>DAS DECLARAÇÕES FINAIS.</b> Declaram as partes e o
advogado a integral concordância com os termos desta escritura, que constitui
título hábil para o registro imobiliário. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-NOMEACAO-INVENTARIANTE",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de nomeação de inventariante e declarações do espólio",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento virem que, aos
[DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano
de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram o meeiro e os herdeiros a seguir
qualificados: {{ outorgantes }}, reconhecidos como os próprios por mim,
tabelião, do que dou fé. E, pelos comparecentes, me foi dito que
[NOME COMPLETO DO AUTOR DA HERANÇA] faleceu em [DATA DO ÓBITO], na cidade de
[LUGAR DO ÓBITO], conforme certidão de óbito lavrada sob o termo n.
[TERMO DO ÓBITO], no Livro [LIVRO DO ÓBITO], folhas [FOLHAS DO ÓBITO], do
[SERVENTIA DO REGISTRO DO ÓBITO], e que, antes da confecção da escritura
pública definitiva de partilha, e na forma do artigo 810 do Código de Normas,
prestam as seguintes declarações e nomeiam representante ao espólio. <b>DA
NOMEAÇÃO.</b> Nomeiam, de comum acordo, [NOME E QUALIFICAÇÃO DO INVENTARIANTE]
para representar o espólio, conferindo-lhe poderes para representá-lo perante
estabelecimentos bancários e instituições fiscais, para acessar dados bancários
e fiscais relevantes ao inventário e à partilha, e para tornar viável a
transferência de titularidade de conta bancária da pessoa falecida.
<b>DAS DECLARAÇÕES.</b> Declaram os comparecentes que
[DECLARAÇÕES SOBRE O ACERVO, OS HERDEIROS E O ESTADO DO ESPÓLIO], e que não
têm conhecimento de testamento deixado pelo autor da herança. <b>DA
ADVERTÊNCIA.</b> FICAM OS COMPARECENTES EXPRESSAMENTE ADVERTIDOS por mim,
tabelião, de que a presente escritura NÃO SUBSTITUI o inventário e a partilha,
NÃO TRANSFERE a propriedade de bem algum e NÃO CONSTITUI título hábil para
ingresso no Registro de Imóveis, prestando-se exclusivamente à representação e
às declarações acima. <b>DOS ADVOGADOS.</b> Assistem as partes
[NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB DO ADVOGADO], que comparece e assina
esta escritura. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    # =================================================== FAMÍLIA

    {
        "codigo": "NT-ESC-DIVORCIO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de divórcio consensual direto",
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
        "corpo": _corpo("""<p>Saibam quantos este
público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias
do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]),
nesta cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como
DIVORCIANDOS {{ outorgantes }}, reconhecidos como os próprios por mim,
tabelião, à vista dos documentos apresentados, do que dou fé. <b>DO
CASAMENTO.</b> Declaram os DIVORCIANDOS que se casaram em [DATA DO CASAMENTO],
sob o regime de [REGIME DE BENS], conforme certidão de casamento expedida em
[DATA DA CERTIDÃO DE CASAMENTO], lavrada sob o termo n. [TERMO DO CASAMENTO], no
Livro [LIVRO DO CASAMENTO], folhas [FOLHAS DO CASAMENTO], do
[SERVENTIA DO REGISTRO DO CASAMENTO]. «SE HOUVE PACTO ANTENUPCIAL: O regime de
bens foi estipulado por pacto antenupcial lavrado em [DATA DO PACTO
ANTENUPCIAL], registrado sob o n. [REGISTRO DO PACTO ANTENUPCIAL] no
[CARTÓRIO DO REGISTRO DO PACTO].» <b>DA VONTADE DE DIVORCIAR-SE.</b> Declaram
os DIVORCIANDOS, de forma espontânea e isenta de vícios, que é firme e definitiva
a vontade de dissolver o vínculo conjugal, requerendo o DIVÓRCIO na forma do
artigo 226, § 6º, da Constituição Federal. <b>DOS FILHOS.</b>
{FILHOS: Declaram os DIVORCIANDOS não haver filhos comuns | Declaram os
DIVORCIANDOS haver os seguintes filhos comuns, todos maiores e capazes:
[NOMES E QUALIFICAÇÃO DOS FILHOS MAIORES] | Declaram os DIVORCIANDOS haver os
seguintes filhos comuns incapazes ou nascituros: [NOMES E DATAS DE NASCIMENTO
DOS FILHOS INCAPAZES]}. «SE HOUVER FILHO INCAPAZ OU NASCITURO: FICA CONSIGNADO
EXPRESSAMENTE, na forma do artigo 822, § 1º, do Código de Normas, que esta
escritura NÃO CONTÉM E NÃO PODE CONTER qualquer previsão relativa a guarda,
visitação e alimentos dos filhos incapazes ou nascituros, e que os DIVORCIANDOS
SE COMPROMETEM A LEVAR ESSAS QUESTÕES AO PODER JUDICIÁRIO, observadas as regras
de competência do Código de Processo Civil.» <b>DA PARTILHA DE BENS.</b>
{PARTILHA: Declaram os DIVORCIANDOS que não possuem bens comuns a partilhar |
Declaram os DIVORCIANDOS que os bens comuns são partilhados da seguinte forma:
[DESCRIÇÃO E PARTILHA DOS BENS COMUNS, COM VALORES] | Declaram os DIVORCIANDOS
que possuem bens comuns e que deixam a partilha para momento posterior, na forma
do artigo 1.581 do Código Civil}. <b>DA PENSÃO ALIMENTÍCIA ENTRE OS
CÔNJUGES.</b> {ALIMENTOS: Declaram os DIVORCIANDOS que dispensam mutuamente
alimentos, deles abrindo mão de forma irrevogável | Fica ajustado que
[NOME DE QUEM PAGA] pagará a [NOME DE QUEM RECEBE] pensão alimentícia mensal de
[VALOR DA PENSÃO POR EXTENSO] ([VALOR DA PENSÃO EM ALGARISMOS]), reajustável por
[CRITÉRIO DE REAJUSTE], até [PRAZO DA PENSÃO], mediante depósito em
[FORMA DE PAGAMENTO DA PENSÃO]}. <b>DO NOME.</b>
{NOME: Declaram os DIVORCIANDOS que ambos manterão o nome de casados |
[NOME DE QUEM ALTERA] voltará a usar o nome de solteiro, qual seja,
[NOME DE SOLTEIRO], devendo o registro civil proceder à devida averbação}.
<b>DOS ADVOGADOS.</b> Assistem os DIVORCIANDOS neste ato
[NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB, COM SEÇÃO E UNIDADE DA FEDERAÇÃO, DO
ADVOGADO OU ADVOGADOS], que comparecem e assinam esta escritura, na forma do
artigo 822, § 5º, do Código de Normas. <b>DAS DECLARAÇÕES FINAIS.</b>
«SE HOUVER PROCESSO JUDICIAL: Foi apresentada certidão do juízo competente
informando a [SITUAÇÃO DO PROCESSO: SUSPENSÃO OU DESISTÊNCIA] do processo n.
[NÚMERO DO PROCESSO JUDICIAL].» Ficam os DIVORCIANDOS cientes de que esta
escritura NÃO DEPENDE de homologação judicial e constitui título hábil para o
registro civil, para o registro de imóveis e para o levantamento de importância
depositada em instituições financeiras, na forma do artigo 822, § 4º, do Código
de Normas, e de que devem apresentar o traslado no registro civil do assento de
casamento para a devida averbação. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-SEPARACAO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de separação consensual",
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
        "corpo": _corpo("""<p>Saibam quantos este público
instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês
de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como SEPARANDOS
{{ outorgantes }}, reconhecidos como os próprios por mim, tabelião, do que dou
fé. <b>DO CASAMENTO.</b> Declaram os SEPARANDOS que se casaram em
[DATA DO CASAMENTO], sob o regime de [REGIME DE BENS], conforme certidão de
casamento expedida em [DATA DA CERTIDÃO DE CASAMENTO], lavrada sob o termo n.
[TERMO DO CASAMENTO], no Livro [LIVRO DO CASAMENTO], folhas
[FOLHAS DO CASAMENTO], do [SERVENTIA DO REGISTRO DO CASAMENTO]. <b>DA VONTADE
DE SEPARAR-SE.</b> Declaram os SEPARANDOS, de forma ESPONTÂNEA E ISENTA DE
VÍCIOS, na forma do artigo 823, I, do Código de Normas, que não mais desejam
manter a sociedade conjugal e que pretendem a SEPARAÇÃO conforme as cláusulas
ora ajustadas. FICAM OS SEPARANDOS EXPRESSAMENTE ADVERTIDOS por mim, tabelião,
de que a separação dissolve a SOCIEDADE conjugal mas NÃO O VÍNCULO MATRIMONIAL,
razão pela qual não poderão contrair novo casamento enquanto não convertida a
separação em divórcio. <b>DOS FILHOS.</b> {FILHOS: Declaram os SEPARANDOS não
haver filhos comuns | Declaram os SEPARANDOS haver os seguintes filhos comuns,
todos maiores e capazes: [NOMES E QUALIFICAÇÃO DOS FILHOS MAIORES] | Declaram os
SEPARANDOS haver os seguintes filhos comuns incapazes ou nascituros:
[NOMES E DATAS DE NASCIMENTO DOS FILHOS INCAPAZES]}. «SE HOUVER FILHO INCAPAZ OU
NASCITURO: FICA CONSIGNADO EXPRESSAMENTE, na forma do artigo 822, § 1º, do
Código de Normas, que esta escritura NÃO CONTÉM E NÃO PODE CONTER qualquer
previsão relativa a guarda, visitação e alimentos dos filhos incapazes ou
nascituros, e que os SEPARANDOS SE COMPROMETEM A LEVAR ESSAS QUESTÕES AO PODER
JUDICIÁRIO.» <b>DA PARTILHA DE BENS.</b> {PARTILHA: Declaram os SEPARANDOS que
não possuem bens comuns a partilhar | Declaram os SEPARANDOS que os bens comuns
são partilhados da seguinte forma: [DESCRIÇÃO E PARTILHA DOS BENS COMUNS, COM
VALORES] | Declaram os SEPARANDOS que deixam a partilha para momento posterior}.
<b>DA PENSÃO ALIMENTÍCIA ENTRE OS CÔNJUGES.</b> {ALIMENTOS: Declaram os
SEPARANDOS que dispensam mutuamente alimentos | Fica ajustado que
[NOME DE QUEM PAGA] pagará a [NOME DE QUEM RECEBE] pensão alimentícia mensal de
[VALOR DA PENSÃO POR EXTENSO] ([VALOR DA PENSÃO EM ALGARISMOS]), reajustável por
[CRITÉRIO DE REAJUSTE]}. <b>DO NOME.</b> {NOME: Declaram os SEPARANDOS que ambos
manterão o nome de casados | [NOME DE QUEM ALTERA] voltará a usar o nome de
solteiro, qual seja, [NOME DE SOLTEIRO]}. <b>DOS ADVOGADOS.</b> Assistem os
SEPARANDOS [NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB, COM SEÇÃO E UNIDADE DA
FEDERAÇÃO, DO ADVOGADO], que comparece e assina esta escritura. <b>DAS
DECLARAÇÕES FINAIS.</b> Ficam os SEPARANDOS cientes de que devem apresentar o
traslado no registro civil do assento de casamento para a devida averbação.
Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-CONVERSAO-DIVORCIO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de conversão de separação em divórcio",
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
        "corpo": _corpo("""<p>Saibam
quantos este público instrumento virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram como DIVORCIANDOS {{ outorgantes }},
reconhecidos como os próprios por mim, tabelião, do que dou fé. <b>DO CASAMENTO
E DA SEPARAÇÃO.</b> Declaram os DIVORCIANDOS que se casaram em
[DATA DO CASAMENTO], sob o regime de [REGIME DE BENS], conforme certidão de
casamento lavrada sob o termo n. [TERMO DO CASAMENTO], no Livro
[LIVRO DO CASAMENTO], folhas [FOLHAS DO CASAMENTO], do
[SERVENTIA DO REGISTRO DO CASAMENTO], e que se separaram
{SEPARAÇÃO: judicialmente, conforme sentença proferida nos autos do processo n.
[NÚMERO DO PROCESSO DE SEPARAÇÃO] | extrajudicialmente, conforme escritura
pública lavrada em [DATA DA ESCRITURA DE SEPARAÇÃO], no Livro
[LIVRO DA ESCRITURA DE SEPARAÇÃO], folhas [FOLHAS DA ESCRITURA DE SEPARAÇÃO], do
[SERVENTIA DA ESCRITURA DE SEPARAÇÃO]}. Foi-me apresentada e fica arquivada a
certidão da averbação da separação no assento de casamento, averbação feita em
[DATA DA AVERBAÇÃO DA SEPARAÇÃO], sendo ela BASTANTE para este ato e DISPENSADA
a certidão atualizada do processo judicial, na forma do artigo 830 do Código de
Normas e do artigo 52 da Resolução n. 35 do Conselho Nacional de Justiça. <b>DA CONVERSÃO.</b> Declaram os DIVORCIANDOS,
de forma espontânea e isenta de vícios, que é firme e definitiva a vontade de
CONVERTER a separação em DIVÓRCIO, dissolvendo o vínculo matrimonial na forma do
artigo 226, § 6º, da Constituição Federal. <b>DAS CONDIÇÕES.</b>
{CONDIÇÕES: Declaram os DIVORCIANDOS que MANTÊM integralmente as condições
convencionadas na separação, nada havendo a alterar | Declaram os DIVORCIANDOS
que ALTERAM as condições convencionadas na separação, nos seguintes termos:
[ALTERAÇÕES ÀS CONDIÇÕES DA SEPARAÇÃO]}. <b>DOS FILHOS.</b>
{FILHOS: Declaram os DIVORCIANDOS não haver filhos comuns | Declaram haver os
seguintes filhos comuns, todos maiores e capazes: [NOMES E QUALIFICAÇÃO DOS
FILHOS MAIORES] | Declaram haver filhos comuns incapazes ou nascituros:
[NOMES E DATAS DE NASCIMENTO DOS FILHOS INCAPAZES]}. «SE HOUVER FILHO INCAPAZ OU
NASCITURO: FICA CONSIGNADO EXPRESSAMENTE que esta conversão NÃO ALTERA em nada o
que foi convencionado e homologado na separação em relação aos direitos desses
filhos, razão pela qual é cabível a via extrajudicial na forma do artigo 822,
§ 2º, do Código de Normas.» <b>DA PARTILHA DE BENS.</b>
{PARTILHA: A partilha dos bens comuns já foi realizada na separação, nada
havendo a partilhar | Os bens comuns são agora partilhados da seguinte forma:
[DESCRIÇÃO E PARTILHA DOS BENS COMUNS, COM VALORES] | Os DIVORCIANDOS deixam a
partilha para momento posterior}. <b>DA PENSÃO ALIMENTÍCIA ENTRE OS
CÔNJUGES.</b> {ALIMENTOS: Ficam mantidos os alimentos ajustados na separação,
nos mesmos termos | Declaram os DIVORCIANDOS que dispensam mutuamente
alimentos, deles abrindo mão de forma irrevogável | Fica ajustado que
[NOME DE QUEM PAGA] pagará a [NOME DE QUEM RECEBE] pensão alimentícia mensal de
[VALOR DA PENSÃO POR EXTENSO] ([VALOR DA PENSÃO EM ALGARISMOS]), reajustável por
[CRITÉRIO DE REAJUSTE]}. <b>DO NOME.</b> {NOME: Ambos manterão o nome
que ora usam | [NOME DE QUEM ALTERA] voltará a usar o nome de solteiro, qual
seja, [NOME DE SOLTEIRO]}. <b>DOS ADVOGADOS.</b> Assistem os DIVORCIANDOS
[NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB, COM SEÇÃO E UNIDADE DA FEDERAÇÃO, DO
ADVOGADO], que comparece e assina esta escritura. <b>DAS DECLARAÇÕES FINAIS.</b>
Ficam os DIVORCIANDOS cientes de que esta escritura não depende de homologação
judicial e de que devem apresentar o traslado no registro civil do assento de
casamento para a devida averbação. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-RESTABELECIMENTO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de restabelecimento da sociedade conjugal",
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
        "corpo": _corpo("""<p>Saibam
quantos este público instrumento virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram como RECONCILIANDOS {{ outorgantes }},
reconhecidos como os próprios por mim, tabelião, do que dou fé. <b>DO CASAMENTO
E DA SEPARAÇÃO.</b> Declaram os RECONCILIANDOS que se casaram em
[DATA DO CASAMENTO], sob o regime de [REGIME DE BENS], conforme certidão de
casamento lavrada sob o termo n. [TERMO DO CASAMENTO], no Livro
[LIVRO DO CASAMENTO], folhas [FOLHAS DO CASAMENTO], do
[SERVENTIA DO REGISTRO DO CASAMENTO], e que se separaram
{SEPARAÇÃO: judicialmente, conforme sentença proferida nos autos do processo n.
[NÚMERO DO PROCESSO DE SEPARAÇÃO], que tramitou perante o
[JUÍZO DA SEPARAÇÃO] | extrajudicialmente, conforme escritura pública lavrada em
[DATA DA ESCRITURA DE SEPARAÇÃO], no Livro [LIVRO DA ESCRITURA DE SEPARAÇÃO],
folhas [FOLHAS DA ESCRITURA DE SEPARAÇÃO], do
[SERVENTIA DA ESCRITURA DE SEPARAÇÃO]}, o que se comprova pela certidão que me
foi apresentada e fica arquivada, necessária e suficiente para este ato na forma
do artigo 828 do Código de Normas. <b>DO RESTABELECIMENTO.</b> Declaram os
RECONCILIANDOS, de forma espontânea e isenta de vícios, que é firme a vontade de
RESTABELECER A SOCIEDADE CONJUGAL, que passa a vigorar nos mesmos termos em que
foi constituída, com o mesmo regime de bens, sem prejuízo dos direitos de
terceiros adquiridos antes e durante a separação, qualquer que tenha sido o
regime, na forma do artigo 1.577 e seu parágrafo único do Código Civil. <b>DA
ORIENTAÇÃO PRESTADA.</b> FICAM OS RECONCILIANDOS EXPRESSAMENTE ORIENTADOS por
mim, tabelião, na forma do artigo 829, I, do Código de Normas, sobre a
NECESSIDADE DE APRESENTAR O TRASLADO desta escritura no registro civil do
assento de casamento, para a devida averbação, e cientes de que a averbação do
restabelecimento somente poderá ser efetivada depois da averbação da separação,
podendo ambas ser simultâneas. «SE SEPARAÇÃO LAVRADA NESTA SERVENTIA: Procedi,
nesta data, à anotação do presente restabelecimento à margem da escritura pública
de separação consensual, na forma do artigo 829, II, do Código de Normas.»
«SE SEPARAÇÃO LAVRADA EM OUTRA SERVENTIA: Será comunicado o presente
restabelecimento ao tabelionato que lavrou a escritura de separação, para a
anotação necessária, na forma do artigo 829, II, do Código de Normas.»
«SE SEPARAÇÃO JUDICIAL: Será comunicado o presente restabelecimento ao juízo da
separação judicial, na forma do artigo 829, III, do Código de Normas.» <b>DOS
ADVOGADOS.</b> Assistem os RECONCILIANDOS [NOME, QUALIFICAÇÃO E INSCRIÇÃO NA
OAB, COM SEÇÃO E UNIDADE DA FEDERAÇÃO, DO ADVOGADO], que comparece e assina esta
escritura. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-UNIAO-ESTAVEL",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública declaratória de união estável",
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
        "corpo": _corpo("""<p>Saibam quantos este
público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias
do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]),
nesta cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como
DECLARANTES {{ outorgantes }}, reconhecidos como os próprios por mim, tabelião,
à vista dos documentos apresentados, do que dou fé. E, pelos DECLARANTES, me foi
dito que convivem em UNIÃO ESTÁVEL desde [DATA DE INÍCIO DA UNIÃO], de forma
PÚBLICA, CONTÍNUA E DURADOURA, estabelecida com o objetivo de constituição de
família, na forma do artigo 1.723 do Código Civil e do artigo 226, § 3º, da
Constituição Federal. Declaram, SOB AS PENAS DA LEI, que não incidem em nenhum
dos impedimentos do artigo 1.521 do Código Civil, «SE SEPARADO DE FATO:
ressalvando que [NOME DE QUEM É CASADO] é casado mas se acha separado de fato
desde [DATA DA SEPARAÇÃO DE FATO], hipótese em que a lei admite a união estável,
na forma do artigo 1.723, § 1º, do Código Civil». <b>DO REGIME DE BENS.</b>
{REGIME: Declaram os conviventes que, não havendo estipulação em contrário,
aplica-se à união o regime da COMUNHÃO PARCIAL DE BENS, na forma do artigo 1.725
do Código Civil | Declaram os conviventes que estipulam, para reger as relações
patrimoniais da união, o regime da [REGIME DE BENS ESTIPULADO], com os seguintes
efeitos: [EFEITOS PATRIMONIAIS ESTIPULADOS]}. <b>DOS FILHOS.</b>
{FILHOS: Declaram os conviventes não haver filhos comuns | Declaram os
conviventes haver os seguintes filhos comuns: [NOMES E DATAS DE NASCIMENTO DOS
FILHOS]}. <b>DAS DECLARAÇÕES FINAIS.</b> Declaram os conviventes que a presente
escritura produz efeitos desde a data de início da união acima declarada, e que
estão cientes de que a declaração aqui feita não supre o registro de nascimento
de eventuais filhos nem substitui os atos próprios do registro civil. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de dissolução de união estável",
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
        "corpo": _corpo("""<p>Saibam quantos este
público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias
do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]),
nesta cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia,
perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como
CONVIVENTES {{ outorgantes }}, reconhecidos como os próprios por mim, tabelião,
do que dou fé. <b>DA UNIÃO.</b> Declaram os CONVIVENTES que mantiveram união
estável no período de [DATA DE INÍCIO DA UNIÃO] a [DATA DO FIM DA UNIÃO],
«SE HOUVE ESCRITURA DECLARATÓRIA: união declarada por escritura pública lavrada
em [DATA DA ESCRITURA DECLARATÓRIA], no Livro [LIVRO DA ESCRITURA DECLARATÓRIA],
folhas [FOLHAS DA ESCRITURA DECLARATÓRIA], do
[SERVENTIA DA ESCRITURA DECLARATÓRIA]», sob o regime de [REGIME DE BENS DA
UNIÃO]. <b>DA DISSOLUÇÃO.</b> Declaram os CONVIVENTES, de forma espontânea e
isenta de vícios, que é firme e definitiva a vontade de DISSOLVER a união
estável, que se considera extinta desde [DATA DO FIM DA UNIÃO]. <b>DOS
FILHOS.</b> {FILHOS: Declaram os CONVIVENTES não haver filhos comuns | Declaram
haver os seguintes filhos comuns, todos maiores e capazes:
[NOMES E QUALIFICAÇÃO DOS FILHOS MAIORES] | Declaram haver filhos comuns
incapazes ou nascituros: [NOMES E DATAS DE NASCIMENTO DOS FILHOS INCAPAZES]}.
«SE HOUVER FILHO INCAPAZ OU NASCITURO: FICA CONSIGNADO EXPRESSAMENTE, na forma
do artigo 822, § 1º, do Código de Normas, que esta escritura NÃO CONTÉM E NÃO
PODE CONTER qualquer previsão relativa a guarda, visitação e alimentos desses
filhos, e que os CONVIVENTES SE COMPROMETEM A LEVAR ESSAS QUESTÕES AO PODER
JUDICIÁRIO.» <b>DA PARTILHA DE BENS.</b> {PARTILHA: Declaram os CONVIVENTES que
não possuem bens comuns a partilhar | Declaram os CONVIVENTES que os bens comuns
são partilhados da seguinte forma: [DESCRIÇÃO E PARTILHA DOS BENS COMUNS, COM
VALORES] | Declaram os CONVIVENTES que deixam a partilha para momento
posterior}. <b>DA PENSÃO ALIMENTÍCIA.</b> {ALIMENTOS: Declaram os CONVIVENTES
que dispensam mutuamente alimentos | Fica ajustado que [NOME DE QUEM PAGA]
pagará a [NOME DE QUEM RECEBE] pensão alimentícia mensal de
[VALOR DA PENSÃO POR EXTENSO] ([VALOR DA PENSÃO EM ALGARISMOS])}. <b>DO
NOME.</b> {NOME: Nada há a alterar quanto ao nome dos CONVIVENTES |
[NOME DE QUEM ALTERA] voltará a usar o nome de solteiro, qual seja,
[NOME DE SOLTEIRO]}. <b>DOS ADVOGADOS.</b> Assistem os CONVIVENTES
[NOME, QUALIFICAÇÃO E INSCRIÇÃO NA OAB, COM SEÇÃO E UNIDADE DA FEDERAÇÃO, DO
ADVOGADO], que comparece e assina esta escritura. «SE HOUVE ESCRITURA
DECLARATÓRIA NESTA SERVENTIA: Procedi, nesta data, à anotação da presente
dissolução à margem da escritura declaratória de união estável.» Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    # =================================================== GARANTIA E DÍVIDA

    {
        "codigo": "NT-ESC-HIPOTECA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de hipoteca",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram: como DEVEDOR
HIPOTECANTE, {{ outorgantes }}; e como CREDOR HIPOTECÁRIO, {{ outorgados }};
reconhecidos como os próprios por mim, tabelião, à vista dos documentos
apresentados, do que dou fé. <b>DA DÍVIDA.</b> Declara o DEVEDOR HIPOTECANTE que
é devedor do CREDOR HIPOTECÁRIO da quantia de [VALOR DA DÍVIDA POR EXTENSO]
([VALOR DA DÍVIDA EM ALGARISMOS]), proveniente de [ORIGEM DA DÍVIDA], a ser paga
{PAGAMENTO: de uma só vez, em [DATA DO VENCIMENTO] | em
[NÚMERO DE PARCELAS POR EXTENSO] ([NÚMERO DE PARCELAS EM ALGARISMOS]) parcelas
mensais e sucessivas de [VALOR DA PARCELA POR EXTENSO] ([VALOR DA PARCELA EM
ALGARISMOS]), vencendo-se a primeira em [DATA DA PRIMEIRA PARCELA]}, com juros de
[TAXA DE JUROS] e correção por [CRITÉRIO DE CORREÇÃO]. <b>DO IMÓVEL DADO EM
GARANTIA.</b> Para garantia da dívida acima especificada, o DEVEDOR HIPOTECANTE
dá em HIPOTECA {GRAU: de primeiro grau | de segundo grau, subsistindo a hipoteca
anterior registrada sob o n. [REGISTRO DA HIPOTECA ANTERIOR]} ao CREDOR
HIPOTECÁRIO o seguinte imóvel, de sua exclusiva propriedade:
[DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA, COM CARACTERÍSTICAS, CONFRONTAÇÕES E
LOCALIZAÇÃO], objeto da matrícula n. [MATRÍCULA] do
[CARTÓRIO DE REGISTRO DE IMÓVEIS], havido conforme registro n.
[NÚMERO DO REGISTRO ANTERIOR], ao qual as partes atribuem o valor de
[VALOR DO IMÓVEL POR EXTENSO] ([VALOR DO IMÓVEL EM ALGARISMOS]). <b>DAS
CONDIÇÕES.</b> A presente hipoteca vigorará pelo prazo de
[PRAZO DA HIPOTECA POR EXTENSO] ([PRAZO DA HIPOTECA EM ALGARISMOS]) anos, não
excedendo o limite de trinta anos do artigo 1.485 do Código Civil. Obriga-se o
DEVEDOR HIPOTECANTE a conservar o imóvel, a não aliená-lo nem gravá-lo sem o
consentimento escrito do CREDOR HIPOTECÁRIO, e a manter em dia os tributos e
encargos que sobre ele recaiam. CONSIGNO EXPRESSAMENTE, na forma do artigo 1.428
do Código Civil, que É NULA a cláusula que autorize o CREDOR HIPOTECÁRIO a ficar
com o imóvel se a dívida não for paga no vencimento, razão pela qual nenhuma
estipulação neste sentido consta deste instrumento. «SE OUTORGA CONJUGAL:
Comparece ainda ao ato, para dar a competente outorga, o cônjuge do DEVEDOR
HIPOTECANTE, [NOME E QUALIFICAÇÃO DO CÔNJUGE], que anui à presente hipoteca em
todos os seus termos, na forma do artigo 1.647, I, do Código Civil.»
<b>DA ACEITAÇÃO.</b> Pelo CREDOR HIPOTECÁRIO me foi dito que aceita esta
escritura em todos os seus termos. Ficam as partes cientes de que a hipoteca
vale entre elas desde já, mas SOMENTE PRODUZ EFEITO CONTRA TERCEIROS depois de
registrada no Registro de Imóveis competente, na forma dos artigos 1.227 e 1.492
do Código Civil. Foram-me apresentados e ficam arquivados: a certidão atualizada
da matrícula, expedida em [DATA DA CERTIDÃO DA MATRÍCULA]; e a certidão de ônus
reais. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-ALIENACAO-FIDUCIARIA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de alienação fiduciária de bem imóvel",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram: como FIDUCIANTE, {{ outorgantes }}; e como
FIDUCIÁRIO, {{ outorgados }}; reconhecidos como os próprios por mim, tabelião,
do que dou fé. <b>DO PRINCIPAL DA DÍVIDA.</b> Declara o FIDUCIANTE que é devedor
do FIDUCIÁRIO da quantia principal de [VALOR DO PRINCIPAL POR EXTENSO]
([VALOR DO PRINCIPAL EM ALGARISMOS]), proveniente de [ORIGEM DA DÍVIDA]. <b>DO
PRAZO E DAS CONDIÇÕES DE REPOSIÇÃO.</b> A dívida será reposta em
[NÚMERO DE PARCELAS POR EXTENSO] ([NÚMERO DE PARCELAS EM ALGARISMOS]) parcelas
mensais e sucessivas de [VALOR DA PARCELA POR EXTENSO]
([VALOR DA PARCELA EM ALGARISMOS]), vencendo-se a primeira em
[DATA DA PRIMEIRA PARCELA] e a última em [DATA DA ÚLTIMA PARCELA], mediante
[FORMA DE PAGAMENTO DAS PARCELAS]. <b>DA TAXA DE JUROS E DOS ENCARGOS.</b>
Incidem sobre a dívida juros de [TAXA DE JUROS], correção monetária por
[ÍNDICE DE CORREÇÃO], e os seguintes encargos: [ENCARGOS INCIDENTES]. <b>DA
CONSTITUIÇÃO DA PROPRIEDADE FIDUCIÁRIA.</b> Em garantia do pagamento, o
FIDUCIANTE ALIENA FIDUCIARIAMENTE ao FIDUCIÁRIO, transferindo-lhe a propriedade
resolúvel e a posse indireta, o seguinte imóvel:
[DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA], objeto da matrícula n. [MATRÍCULA]
do [CARTÓRIO DE REGISTRO DE IMÓVEIS], por ele adquirido conforme
[TÍTULO E MODO DE AQUISIÇÃO DO IMÓVEL], registro n.
[NÚMERO DO REGISTRO ANTERIOR]. <b>DA LIVRE UTILIZAÇÃO PELO FIDUCIANTE.</b> Fica
assegurada ao FIDUCIANTE, enquanto adimplente, a LIVRE UTILIZAÇÃO do imóvel, por
sua conta e risco, na forma do artigo 24, V, da Lei n. 9.514, de 1997. <b>DO
VALOR DO IMÓVEL PARA LEILÃO.</b> Para efeito de venda em público leilão, as
partes atribuem ao imóvel o valor de [VALOR DO IMÓVEL PARA LEILÃO POR EXTENSO]
([VALOR DO IMÓVEL PARA LEILÃO EM ALGARISMOS]), que será revisto segundo o
seguinte critério: [CRITÉRIO DE REVISÃO DO VALOR DO IMÓVEL]. <b>DO PROCEDIMENTO
EM CASO DE INADIMPLEMENTO.</b> Vencida e não paga, no todo ou em parte, a dívida,
e constituído em mora o FIDUCIANTE, observar-se-á integralmente o procedimento
dos artigos 26 e 27 da Lei n. 9.514, de 1997, a saber: o FIDUCIANTE será
INTIMADO, a requerimento do FIDUCIÁRIO, pelo Oficial do Registro de Imóveis,
para satisfazer, no prazo de QUINZE DIAS, a prestação vencida e as que se
vencerem até a data do pagamento, os juros convencionais, as penalidades e os
demais encargos; purgada a mora, convalesce o contrato; não purgada, e
consolidada a propriedade em nome do FIDUCIÁRIO, este promoverá PÚBLICO LEILÃO
nos prazos e condições do artigo 27, restituindo ao FIDUCIANTE a importância que
sobejar, se houver. <b>DA ACEITAÇÃO E DO REGISTRO.</b> Pelo FIDUCIÁRIO me foi
dito que aceita esta escritura em todos os seus termos. Ficam as partes cientes
de que A PROPRIEDADE FIDUCIÁRIA SOMENTE SE CONSTITUI COM O REGISTRO desta
escritura no Registro de Imóveis competente, na forma do artigo 23 da Lei n.
9.514, de 1997. «SE OUTORGA CONJUGAL: Comparece ainda ao ato, para dar a
competente outorga, o cônjuge do FIDUCIANTE, [NOME E QUALIFICAÇÃO DO CÔNJUGE],
que anui à presente alienação fiduciária em todos os seus termos.» Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-CONFISSAO-DACAO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de confissão de dívida e dação em pagamento",
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
        "corpo": _corpo("""<p>Saibam
quantos este público instrumento virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram: como DEVEDOR, {{ outorgantes }}; e como
CREDOR, {{ outorgados }}; reconhecidos como os próprios por mim, tabelião, do
que dou fé. <b>DA CONFISSÃO DA DÍVIDA.</b> Declara o DEVEDOR, de forma livre e
espontânea, que CONFESSA dever ao CREDOR a quantia certa e líquida de
[VALOR DA DÍVIDA POR EXTENSO] ([VALOR DA DÍVIDA EM ALGARISMOS]), proveniente de
[ORIGEM DA DÍVIDA], vencida em [DATA DO VENCIMENTO DA DÍVIDA], reconhecendo-a
como dívida líquida, certa e exigível. <b>DA DAÇÃO EM PAGAMENTO.</b> Para
solver integralmente a dívida ora confessada, e COM O EXPRESSO CONSENTIMENTO DO
CREDOR em receber prestação diversa da que lhe é devida, na forma do artigo 356
do Código Civil, o DEVEDOR DÁ EM PAGAMENTO ao CREDOR o seguinte imóvel, de sua
exclusiva propriedade: [DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA], objeto da
matrícula n. [MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS], havido conforme
registro n. [NÚMERO DO REGISTRO ANTERIOR], ao qual as partes atribuem o preço
certo de [VALOR ATRIBUÍDO AO IMÓVEL POR EXTENSO]
([VALOR ATRIBUÍDO AO IMÓVEL EM ALGARISMOS]). <b>DAS RELAÇÕES ENTRE AS PARTES.</b>
Determinado o preço da coisa dada em pagamento, as relações entre as partes
regem-se pelas normas do contrato de compra e venda, na forma do artigo 357 do
Código Civil. {SALDO: A dação solve integralmente a dívida, nada mais podendo
ser reclamado a qualquer título | Sendo o valor do imóvel inferior ao da dívida,
remanesce em favor do CREDOR o saldo de [VALOR DO SALDO POR EXTENSO]
([VALOR DO SALDO EM ALGARISMOS]), a ser pago em [CONDIÇÕES DO SALDO] | Sendo o
valor do imóvel superior ao da dívida, o CREDOR pagou ao DEVEDOR a diferença de
[VALOR DA DIFERENÇA POR EXTENSO] ([VALOR DA DIFERENÇA EM ALGARISMOS]), do que
este dá quitação}. <b>DA QUITAÇÃO E DA EVICÇÃO.</b> Dá o CREDOR ao DEVEDOR, pelo
recebimento do imóvel, plena e geral quitação da dívida ora confessada. FICAM AS
PARTES CIENTES, na forma do artigo 359 do Código Civil, de que, se o CREDOR for
EVICTO da coisa recebida em pagamento, RESTABELECER-SE-Á a obrigação primitiva,
ficando sem efeito a quitação ora dada, ressalvados os direitos de terceiros.
«SE OUTORGA CONJUGAL: Comparece ainda ao ato, para dar a competente outorga, o
cônjuge do DEVEDOR, [NOME E QUALIFICAÇÃO DO CÔNJUGE], que anui à presente dação
em todos os seus termos.» Foram-me apresentados e ficam arquivados: a certidão
atualizada da matrícula; e o comprovante de recolhimento do ITBI, guia n.
[NÚMERO DA GUIA DE ITBI], recolhida em [DATA DO ITBI]. Fica consignado que será
emitida a Declaração sobre Operação Imobiliária (DOI). Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-PERMUTA",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de permuta",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como PERMUTANTES
{{ outorgantes }}, reconhecidos como os próprios por mim, tabelião, do que dou
fé. <b>DO PRIMEIRO IMÓVEL.</b> Declara o PRIMEIRO PERMUTANTE,
[NOME DO PRIMEIRO PERMUTANTE], que é senhor e legítimo possuidor do imóvel a
seguir descrito: [DESCRIÇÃO DO PRIMEIRO IMÓVEL CONFORME A MATRÍCULA], objeto da
matrícula n. [MATRÍCULA DO PRIMEIRO IMÓVEL] do
[CARTÓRIO DO PRIMEIRO IMÓVEL], ao qual atribui o valor de
[VALOR DO PRIMEIRO IMÓVEL POR EXTENSO] ([VALOR DO PRIMEIRO IMÓVEL EM
ALGARISMOS]). <b>DO SEGUNDO IMÓVEL.</b> Declara o SEGUNDO PERMUTANTE,
[NOME DO SEGUNDO PERMUTANTE], que é senhor e legítimo possuidor do imóvel a
seguir descrito: [DESCRIÇÃO DO SEGUNDO IMÓVEL CONFORME A MATRÍCULA], objeto da
matrícula n. [MATRÍCULA DO SEGUNDO IMÓVEL] do [CARTÓRIO DO SEGUNDO IMÓVEL], ao
qual atribui o valor de [VALOR DO SEGUNDO IMÓVEL POR EXTENSO]
([VALOR DO SEGUNDO IMÓVEL EM ALGARISMOS]). <b>DA PERMUTA.</b> E, por este
instrumento e na melhor forma de direito, os PERMUTANTES PERMUTAM entre si os
imóveis acima descritos, transmitindo cada um ao outro todo o domínio, direito,
posse e ação que sobre eles exerciam, obrigando-se a fazer esta permuta sempre
boa, firme e valiosa e a responder pela evicção de direito. {TORNA: Sendo os
valores equivalentes, nada há a compensar entre os PERMUTANTES | Sendo os
valores desiguais, [NOME DE QUEM PAGA A TORNA] paga a
[NOME DE QUEM RECEBE A TORNA], a título de TORNA, a quantia de
[VALOR DA TORNA POR EXTENSO] ([VALOR DA TORNA EM ALGARISMOS]), mediante
[FORMA DE PAGAMENTO DA TORNA], do que este dá plena e geral quitação}. <b>DAS
DESPESAS.</b> As despesas deste instrumento correm por conta dos PERMUTANTES em
partes iguais, na forma do artigo 533, I, do Código Civil.
«SE ASCENDENTE E DESCENDENTE: Sendo os PERMUTANTES ascendente e descendente e
desiguais os valores permutados, comparecem ao ato, para consentir
expressamente, na forma do artigo 533, II, do Código Civil, os demais
descendentes e o cônjuge do alienante, a saber:
[NOMES E QUALIFICAÇÃO DE QUEM CONSENTE].» «SE OUTORGA CONJUGAL: Comparecem ainda
ao ato, para dar a competente outorga, os cônjuges dos PERMUTANTES,
[NOMES E QUALIFICAÇÃO DOS CÔNJUGES], que anuem à presente permuta.» Foram-me
apresentadas e ficam arquivadas as certidões atualizadas das duas matrículas e
os comprovantes de recolhimento do ITBI relativos às duas transmissões, guias n.
[NÚMEROS DAS GUIAS DE ITBI], recolhidas em [DATAS DO ITBI]. Fica consignado que
serão emitidas as Declarações sobre Operação Imobiliária (DOI) correspondentes
às duas transmissões. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-QUITACAO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de quitação",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceu como CREDOR
{{ outorgantes }}, reconhecido como o próprio por mim, tabelião, do que dou fé.
E, pelo CREDOR, me foi dito que era credor de [NOME E QUALIFICAÇÃO DO DEVEDOR],
da quantia de [VALOR DA DÍVIDA POR EXTENSO] ([VALOR DA DÍVIDA EM ALGARISMOS]),
proveniente de [ESPÉCIE E ORIGEM DA DÍVIDA], e que recebeu o pagamento integral
daquela quantia em [DATA DO PAGAMENTO], na cidade de [LUGAR DO PAGAMENTO],
{PAGADOR: pelo próprio devedor | por [NOME DE QUEM PAGOU PELO DEVEDOR], que pagou
pelo devedor}, mediante {FORMA DO PAGAMENTO: dinheiro em espécie | transferência
bancária | transferência eletrônica entre contas de pagamento | PIX | cheque n.
[NÚMERO DO CHEQUE], sacado contra o [BANCO DO CHEQUE]}. E que, por este
instrumento e na melhor forma de direito, DÁ AO DEVEDOR PLENA, GERAL,
IRREVOGÁVEL E IRRETRATÁVEL QUITAÇÃO da dívida acima especificada, para nada mais
reclamar em tempo algum, a qualquer título. «SE HOUVER GARANTIA HIPOTECÁRIA: A
dívida ora quitada era garantida por hipoteca sobre o imóvel objeto da matrícula
n. [MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS], registrada sob o n.
[REGISTRO DA HIPOTECA], e o CREDOR AUTORIZA expressamente o CANCELAMENTO daquele
registro, servindo esta escritura de título hábil para tanto, na forma do artigo
1.500 do Código Civil.» «SE HOUVER ALIENAÇÃO FIDUCIÁRIA: A dívida ora quitada
era garantida por alienação fiduciária sobre o imóvel objeto da matrícula n.
[MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS], e o CREDOR requer o
CANCELAMENTO do registro da propriedade fiduciária, com a consequente
consolidação da propriedade plena em nome do fiduciante.» Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-DISTRATO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de distrato",
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
        "corpo": _corpo("""<p>Saibam quantos este público instrumento
virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês de
[MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como DISTRATANTES
{{ outorgantes }}, reconhecidos como os próprios por mim, tabelião, do que dou
fé. <b>DO CONTRATO DESFEITO.</b> Declaram os DISTRATANTES que celebraram entre
si {INSTRUMENTO: escritura pública de [NATUREZA DO CONTRATO DESFEITO], lavrada em
[DATA DO CONTRATO], no Livro [LIVRO DO CONTRATO], folhas [FOLHAS DO CONTRATO],
do [SERVENTIA DO CONTRATO] | instrumento particular de
[NATUREZA DO CONTRATO DESFEITO], firmado em [DATA DO CONTRATO]}, tendo por
objeto [OBJETO DO CONTRATO DESFEITO]. <b>DO DISTRATO.</b> E que, por este
instrumento e na melhor forma de direito, de comum acordo e por mútuo
consentimento, DISTRATAM aquele contrato, tornando-o sem nenhum efeito a partir
desta data, na forma dos artigos 472 e 473 do Código Civil, e observada a mesma
forma exigida para o contrato ora desfeito. <b>DAS RESTITUIÇÕES.</b>
{RESTITUIÇÕES: Declaram os DISTRATANTES que nada há a restituir, por não ter
havido execução do contrato | Em razão do distrato, [NOME DE QUEM RESTITUI]
restitui a [NOME DE QUEM RECEBE] [O QUE É RESTITUÍDO], e
[NOME DE QUEM DEVOLVE O VALOR] devolve a [NOME DE QUEM RECEBE O VALOR] a quantia
de [VALOR RESTITUÍDO POR EXTENSO] ([VALOR RESTITUÍDO EM ALGARISMOS]), mediante
[FORMA DA RESTITUIÇÃO]}. «SE HOUVER RETENÇÃO: Fica retida, a título de
[TÍTULO DA RETENÇÃO], a quantia de [VALOR RETIDO POR EXTENSO]
([VALOR RETIDO EM ALGARISMOS]), com o que os DISTRATANTES expressamente
concordam.» <b>DA QUITAÇÃO RECÍPROCA.</b> Dão-se os DISTRATANTES, mutuamente,
plena, geral e irrevogável quitação de todas as obrigações decorrentes do
contrato ora desfeito, para nada mais reclamarem um do outro, em tempo algum, a
qualquer título. «SE HOUVER REGISTRO A CANCELAR: Requerem os DISTRATANTES o
cancelamento do registro n. [REGISTRO A CANCELAR] da matrícula n. [MATRÍCULA] do
[CARTÓRIO DE REGISTRO DE IMÓVEIS], servindo esta escritura de título hábil para
tanto.» Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    # =================================================== PESSOA E FAMÍLIA

    {
        "codigo": "NT-ESC-EMANCIPACAO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de emancipação",
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
        "corpo": _corpo("""<p>Saibam quantos este público
instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês
de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como OUTORGANTES
{{ outorgantes }}, e, como OUTORGADO EMANCIPANDO, {{ outorgados }}, reconhecidos
como os próprios por mim, tabelião, à vista dos documentos apresentados, do que
dou fé. <b>DA FILIAÇÃO E DA IDADE.</b> Declaram os OUTORGANTES que são
{FILIAÇÃO: os pais | o pai | a mãe} do EMANCIPANDO, nascido em
[DATA DE NASCIMENTO DO EMANCIPANDO], portanto com dezesseis anos completos,
conforme certidão de nascimento lavrada sob o termo n.
[TERMO DO NASCIMENTO], no Livro [LIVRO DO NASCIMENTO], folhas
[FOLHAS DO NASCIMENTO], do [SERVENTIA DO REGISTRO DE NASCIMENTO], que me foi
apresentada e fica arquivada. «SE UM DOS PAIS: Consigna-se que a concessão é
feita por um dos pais na falta do outro, pelo seguinte motivo:
[MOTIVO DA FALTA DO OUTRO GENITOR].» <b>DA CONCESSÃO.</b> E, pelos OUTORGANTES,
me foi dito que, por este instrumento e na melhor forma de direito, CONCEDEM AO
EMANCIPANDO A EMANCIPAÇÃO, cessando para ele a incapacidade civil e a autoridade
parental, na forma do artigo 5º, parágrafo único, I, do Código Civil,
independentemente de homologação judicial. <b>DA MANIFESTAÇÃO DO
EMANCIPANDO.</b> Ouvido por mim, tabelião, o EMANCIPANDO declarou estar ciente
da emancipação ora concedida e de que passará a responder pessoalmente por seus
atos da vida civil. <b>DA ADVERTÊNCIA SOBRE O REGISTRO.</b> FICAM AS PARTES
EXPRESSAMENTE ADVERTIDAS por mim, tabelião, de que a presente emancipação
SOMENTE PRODUZIRÁ EFEITO DEPOIS DE REGISTRADA no Registro Civil das Pessoas
Naturais do domicílio do emancipado, no Livro E, com a devida anotação no assento
de nascimento, na forma dos artigos 89, 90 e 91 da Lei n. 6.015, de 1973, razão
pela qual devem apresentar o traslado desta escritura àquele ofício. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-PACTO-ANTENUPCIAL",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de pacto antenupcial",
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
        "corpo": _corpo("""<p>Saibam quantos este público
instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias do mês
de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta
cidade de {{ sv.ri_cidade }}, Estado do {{ sv.ri_uf }}, nesta serventia, perante
mim, {{ lavrado_nome }}, {{ lavrado_titulo }}, compareceram como NUBENTES
{{ outorgantes }}, reconhecidos como os próprios por mim, tabelião, à vista dos
documentos apresentados, do que dou fé. <b>DO CASAMENTO PROJETADO.</b> Declaram
os NUBENTES que pretendem contrair matrimônio {HABILITAÇÃO: perante o
[SERVENTIA DA HABILITAÇÃO], onde correm os autos de habilitação n.
[NÚMERO DA HABILITAÇÃO] | e que ainda promoverão a habilitação perante o
registro civil competente}. <b>DO REGIME DE BENS ESCOLHIDO.</b> E, pelos
NUBENTES, me foi dito que, por este instrumento e na melhor forma de direito,
ESTIPULAM que o casamento será regido pelo regime da
{REGIME: COMUNHÃO UNIVERSAL DE BENS, comunicando-se todos os bens presentes e
futuros dos cônjuges e suas dívidas passivas, com as exceções do artigo 1.668 do
Código Civil | SEPARAÇÃO TOTAL DE BENS, permanecendo cada cônjuge na exclusiva
propriedade, posse e administração de seus bens presentes e futuros, e podendo
livremente aliená-los ou gravá-los de ônus real, na forma do artigo 1.687 do
Código Civil | PARTICIPAÇÃO FINAL NOS AQUESTOS, na forma dos artigos 1.672 a
1.686 do Código Civil, cabendo a cada cônjuge, à dissolução da sociedade
conjugal, direito à metade dos bens adquiridos pelo casal a título oneroso na
constância do casamento | COMUNHÃO PARCIAL DE BENS, com as cláusulas
complementares a seguir estipuladas}. <b>DAS CLÁUSULAS COMPLEMENTARES.</b>
{COMPLEMENTOS: Nada mais estipulam os NUBENTES além do regime acima escolhido |
Estipulam os NUBENTES, ainda, as seguintes cláusulas:
[CLÁUSULAS COMPLEMENTARES ESTIPULADAS PELOS NUBENTES]}.
«SE PARTICIPAÇÃO FINAL COM LIVRE DISPOSIÇÃO: Convencionam os NUBENTES, na forma
do artigo 1.656 do Código Civil, a LIVRE DISPOSIÇÃO DOS BENS IMÓVEIS
PARTICULARES, dispensada a outorga do outro cônjuge para a alienação ou o
gravame desses bens.» «SE HOUVER BENS A DECLARAR: Declaram os NUBENTES que
possuem, nesta data, os seguintes bens particulares:
[RELAÇÃO DOS BENS PARTICULARES DE CADA NUBENTE].» <b>DAS ADVERTÊNCIAS.</b>
FICAM OS NUBENTES EXPRESSAMENTE ADVERTIDOS por mim, tabelião, de que: o presente
pacto SERÁ INEFICAZ SE NÃO LHE SEGUIR O CASAMENTO, na forma do artigo 1.653 do
Código Civil; é NULA qualquer convenção ou cláusula que contravenha disposição
absoluta de lei, na forma do artigo 1.655; e o pacto SOMENTE PRODUZ EFEITO
PERANTE TERCEIROS depois de REGISTRADO em livro especial no Registro de Imóveis
do domicílio dos cônjuges, na forma do artigo 1.657, razão pela qual devem
apresentar o traslado desta escritura àquele ofício. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-DIRETIVAS-VONTADE",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de diretivas antecipadas de vontade",
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
        "corpo": _corpo("""<p>Saibam quantos
este público instrumento virem que, aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS])
dias do mês de [MÊS POR EXTENSO] do ano de [ANO POR EXTENSO]
([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }}, Estado do
{{ sv.ri_uf }}, {LUGAR: nesta serventia | no endereço [ENDEREÇO DA LAVRATURA],
para onde me desloquei a pedido do declarante}, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceu como DECLARANTE {{ outorgantes }}, reconhecido
como o próprio por mim, tabelião, à vista dos documentos apresentados, do que dou
fé. DOU FÉ de que o DECLARANTE se encontra em pleno gozo de suas faculdades
mentais, orientado no tempo e no espaço, exprimindo sua vontade de forma livre,
consciente e desembaraçada, sem qualquer sinal de coação ou indução. <b>DAS
DIRETIVAS.</b> E, pelo DECLARANTE, me foi dito que, no exercício de sua
autonomia e na forma do artigo 876 do Código de Normas, expressa as seguintes
diretrizes e vontades sobre os cuidados e tratamentos de saúde que deseja, ou
não, receber no momento em que estiver incapacitado de expressar-se de forma
livre e autônoma: [DIRETRIZES E VONTADES SOBRE CUIDADOS E TRATAMENTOS DE SAÚDE].
«SE RECUSA DE TRATAMENTO: Declara expressamente que NÃO DESEJA ser submetido aos
seguintes procedimentos ou tratamentos: [PROCEDIMENTOS E TRATAMENTOS RECUSADOS],
ainda que deles possa resultar prolongamento artificial da vida.»
«SE CUIDADOS PALIATIVOS: Declara desejar receber cuidados paliativos voltados ao
alívio da dor e do sofrimento, com [PREFERÊNCIAS QUANTO AOS CUIDADOS
PALIATIVOS].» «SE DOAÇÃO DE ÓRGÃOS: Declara sua vontade quanto à doação de
órgãos e tecidos nos seguintes termos: [VONTADE QUANTO À DOAÇÃO DE ÓRGÃOS],
ciente de que a manifestação deve ser confirmada por sua família no momento
oportuno, na forma da legislação vigente.» <b>DO PROCURADOR DE SAÚDE.</b>
«SE NOMEAR PROCURADOR DE SAÚDE: Nomeia o DECLARANTE, na forma do artigo 877 do
Código de Normas, como seu PROCURADOR DE SAÚDE,
[NOME E QUALIFICAÇÃO DO PROCURADOR DE SAÚDE], para representá-lo perante médicos
e instituições de saúde, COM O FIM ESPECÍFICO de dar fiel cumprimento às
diretrizes ora estabelecidas, e não para qualquer outra finalidade.
«SE HOUVER SUBSTITUTO: Nomeia, como procurador de saúde substituto, na falta ou
impedimento do primeiro, [NOME E QUALIFICAÇÃO DO PROCURADOR SUBSTITUTO].»»
<b>DAS DECLARAÇÕES FINAIS.</b> Declara o DECLARANTE que estas diretivas poderão
ser por ele revogadas ou alteradas a qualquer tempo, enquanto capaz, por novo
instrumento público. CONSIGNO que, na forma do artigo 880 do Código de Normas, a
existência desta escritura será por mim comunicada, de forma OBRIGATÓRIA,
GRATUITA E SIGILOSA, à Central Notarial de Serviços Eletrônicos Compartilhados,
no módulo Registro Central de Disposições de Última Vontade. Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },

    {
        "codigo": "NT-ESC-USUFRUTO",
        "tipo": "ESCRITURA",
        "nome": "Escritura pública de instituição, reserva ou renúncia de usufruto",
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
        "corpo": _corpo("""<p>Saibam
quantos este público instrumento virem que, aos [DIA POR EXTENSO]
([DIA EM ALGARISMOS]) dias do mês de [MÊS POR EXTENSO] do ano de
[ANO POR EXTENSO] ([ANO EM ALGARISMOS]), nesta cidade de {{ sv.ri_cidade }},
Estado do {{ sv.ri_uf }}, nesta serventia, perante mim, {{ lavrado_nome }},
{{ lavrado_titulo }}, compareceram: como NU-PROPRIETÁRIO, {{ outorgantes }}; e
como USUFRUTUÁRIO, {{ outorgados }}; reconhecidos como os próprios por mim,
tabelião, do que dou fé. <b>DO IMÓVEL.</b> Declaram as partes que o ato tem por
objeto o imóvel a seguir descrito: [DESCRIÇÃO DO IMÓVEL CONFORME A MATRÍCULA],
objeto da matrícula n. [MATRÍCULA] do [CARTÓRIO DE REGISTRO DE IMÓVEIS], havido
conforme registro n. [NÚMERO DO REGISTRO ANTERIOR], ao qual as partes atribuem o
valor de [VALOR DO IMÓVEL POR EXTENSO] ([VALOR DO IMÓVEL EM ALGARISMOS]).
<b>DO ATO.</b> {ATO: E, por este instrumento e na melhor forma de direito, o
NU-PROPRIETÁRIO INSTITUI em favor do USUFRUTUÁRIO o USUFRUTO
{DURAÇÃO: VITALÍCIO | pelo prazo de [PRAZO DO USUFRUTO POR EXTENSO]
([PRAZO DO USUFRUTO EM ALGARISMOS]) anos} sobre o imóvel acima descrito,
ficando o USUFRUTUÁRIO com o direito de usar e fruir do bem, e o
NU-PROPRIETÁRIO com a nua propriedade | E, por este instrumento e na melhor
forma de direito, o USUFRUTUÁRIO RENUNCIA ao usufruto que lhe foi instituído
conforme registro n. [REGISTRO DO USUFRUTO] da referida matrícula,
consolidando-se a propriedade plena em favor do NU-PROPRIETÁRIO, na forma do
artigo 1.410, I, do Código Civil}. <b>DAS CONDIÇÕES DO USUFRUTO.</b> «SE
INSTITUIÇÃO: Fica o USUFRUTUÁRIO obrigado a conservar o imóvel como se seu
fosse, a pagar as despesas ordinárias de conservação e os tributos que sobre ele
recaiam, e a restituí-lo ao fim do usufruto no estado em que o recebeu, salvo as
deteriorações do uso regular. FICAM AS PARTES CIENTES de que o usufruto NÃO SE
TRANSFERE por alienação, podendo apenas o seu exercício ser cedido, na forma do
artigo 1.393 do Código Civil.» «SE PESSOA JURÍDICA: Sendo o USUFRUTUÁRIO pessoa
jurídica, o usufruto extinguir-se-á com ela, ou em TRINTA ANOS da data em que
começar a exercê-lo, na forma do artigo 1.410, III, do Código Civil.» «SE
MAIS DE UM USUFRUTUÁRIO: Sendo o usufruto instituído em favor de duas ou mais
pessoas, {ACRESCIMO: extinguir-se-á parte a parte em relação a cada uma que
falecer, na forma do artigo 1.411 do Código Civil | fica EXPRESSAMENTE
ESTIPULADO que o quinhão do que falecer ACRESCERÁ ao do sobrevivente, na forma
da parte final do artigo 1.411 do Código Civil}.» <b>DOS TRIBUTOS E DO
REGISTRO.</b> Foi apresentado o comprovante de recolhimento do imposto devido,
guia n. [NÚMERO DA GUIA DO IMPOSTO], recolhida em [DATA DO IMPOSTO]. Ficam as
partes cientes de que o ato somente produz efeito depois de
{ATO: REGISTRADO | CANCELADO o registro} no Registro de Imóveis competente.
Nada mais. A presente escritura foi lida e achada conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.</p>
"""),
    },
]


# ----------------------------------------------------------------- carga

def instalar(con, agora: str) -> dict:
    """Poe os modelos no banco, sem atropelar o que a serventia escreveu.

    REPETIVEL POR CONSTRUCAO, COMO O RESTO DO PROJETO
        Entram com origem 'SISTEMA', que e o que o indice unico parcial
        `ux_nt_modelos_origem` cobre. Rodar duas vezes nao duplica.

        O modelo que a serventia editar a mao passa a valer, e o INSERT OR
        IGNORE nao o desfaz: o texto de quem lavra ganha do texto de fabrica.

    E O QUE JA ESTAVA INSTALADO SE ATUALIZA SOZINHO, SE NINGUEM O EDITOU —
    achado em 07/09/2026, ao ajustar o modelo da escritura ao padrao da
    minuta: a linha de `NT-ESC-COMPRA-VENDA-RURAL` tinha entrado em
    17/08/2026, e o `INSERT OR IGNORE` a deixou parada ali, com o texto
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
    for m in MODELOS:
        cur = con.execute(
            """INSERT OR IGNORE INTO nt_modelos
               (codigo, tipo, nome, nome_norm, corpo, fundamento,
                central_censec, natureza_censec, tipo_ato_censec,
                tipo_cesdi, tipo_testamento, com_imovel, ativo,
                origem, origem_chave, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,'SISTEMA',?,?)""",
            (m["codigo"], m["tipo"], m["nome"],
             _norm_nome(m["nome"]), m["corpo"], m.get("fundamentacao"),
             "RCTO" if m.get("tipo_testamento") else
             ("CESDI" if m.get("tipo_cesdi") else "CEP"),
             m.get("natureza_censec"), m.get("tipo_ato_cep"),
             m.get("tipo_cesdi"), m.get("tipo_testamento"),
             m.get("com_imovel", 0), m["codigo"], agora))
        if cur.rowcount:
            resultado["novos"] += 1
            continue
        linha = con.execute(
            "SELECT corpo, fundamento, atualizado_em FROM nt_modelos "
            "WHERE codigo=? AND origem='SISTEMA'", (m["codigo"],)).fetchone()
        corpo_gravado, fundamento_gravado, editado_em = linha[0], linha[1], linha[2]
        if editado_em is not None:
            resultado["ja_existentes"] += 1     # a serventia editou — intocado
            continue
        if corpo_gravado == m["corpo"] and \
                (fundamento_gravado or None) == (m.get("fundamentacao") or None):
            resultado["ja_existentes"] += 1     # já está no que o código diz
            continue
        con.execute(
            "UPDATE nt_modelos SET corpo=?, fundamento=? WHERE codigo=?",
            (m["corpo"], m.get("fundamentacao"), m["codigo"]))
        resultado["atualizados"] += 1
    return resultado


def _norm_nome(texto: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "").upper())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


# ------------------------------------------------------------- utilidades

def por_codigo(codigo: str) -> dict | None:
    for m in MODELOS:
        if m["codigo"] == codigo:
            return m
    return None


def por_tipo(tipo: str) -> list[dict]:
    return [m for m in MODELOS if m["tipo"] == tipo]


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

"""Os modelos do livro do Registro Civil — um por ato, medidos.

    «Elaborar um modelo para cada ato, levando em consideração o que prevê a lei
     6015, o código nacional de normas e, principalmente, o código de normas do
     tjma.» — o oficial, 30/08/2026

DE ONDE SAI O TEXTO — **MUDOU EM 30/08/2026, POR ORDEM DO OFICIAL**

    «Termo de nascimento, casamento e óbito vamos construir os nossos com os
     requisitos legais e regulamentares, **não utilizaremos os modelos ruins do
     e-ofício, nem em papel**.»

    Isto reorienta o módulo, e vale dizer o que mudou. Eu vinha tratando «montado
    dos requisitos» como um **defeito a confessar** — escrevi na tela que o
    casamento e o óbito «não são precedente desta casa», como quem pede
    desculpa. Pela decisão do oficial, montar dos requisitos é o **objetivo**:

      - os **13 modelos do E-Ofício** deixam de ser fonte — são os «modelos
        ruins» de que ele fala;
      - o **termo nº 8.369 em papel** também não é fonte. Ele continua útil
        como conferência — foi nele que se mediu que a ordem dos gêmeos e a
        idade da genitora aparecem no termo desta casa —, mas não manda no
        texto;
      - o que manda são a **Lei nº 6.015/1973**, o **Código Nacional de Normas**
        e, principalmente, o **Código de Normas do TJMA**.

    Os artigos, por ato: nascimento no **art. 233** (que repete o art. 54 da
    Lei); casamento no **art. 70 da Lei nº 6.015/1973**; óbito no **art. 255**
    (que repete o art. 80 da Lei), com os seus doze incisos.

O QUE CADA CLARO É
    Um claro é `{campo}`, e cada um tem nome, rótulo e **de onde vem**. É isso
    que faz o formulário de preenchimento se montar sozinho do modelo — e não
    haver duas listas de campos, uma na tela e outra no texto, para divergirem no
    primeiro conserto.

O QUE ESTE MÓDULO NÃO FAZ
    **Não monta termo de assento importado.** Ordem do oficial no mesmo dia: os
    do acervo têm o termo em papel, assinado, e o sistema guarda deles as
    *informações*, que servem à certidão.

    **A DÍVIDA DOS DOIS GERADORES FOI PAGA EM 31/08/2026.** Até essa data
    `rc_termo.montar` usava `modelos_da_casa` apontando para os 13 do E-Ofício,
    e este comentário dizia que a troca estava por fazer.

    Agora **este módulo é a fonte**: o catálogo aponta para os `TERMO_*` daqui,
    e `rc_termo.montar` busca o corpo em `modelos_da_casa.corpo_de` — sem linha
    na tabela vem o padrão daqui, com linha vem o que o oficial escreveu. Foi a
    **opção B** que ele escolheu, e ela não custou o relato #28: os três termos
    continuam editáveis pela tela, que os confere com `conferir_corpo`, a mesma
    função que a lavratura usa.

    Ver `DOCUMENTACAO/O_TERMO_DA_CASA_E_EDITAVEL.md`.
"""
from __future__ import annotations

from typing import Any


class ModeloError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


FONTE = ("o texto impresso é o do termo nº 8.369 desta casa, de 21/07/1994; os "
         "requisitos são os do art. 233 do Código de Normas do TJMA, que repete "
         "o art. 54 da Lei nº 6.015/1973")


# ------------------------------------------------------- os campos de um termo
#
# **CADA CLARO TEM NOME, ROTULO E PROCEDENCIA**, e e daqui que o formulario de
# preenchimento se monta. Duas listas de campos — uma na tela e outra no texto —
# divergem no primeiro conserto: e a licao da `normalizar_nome`, aplicada ao
# formulario.
def campo(nome: str, rotulo: str, *, de_onde: str = "", exigido: bool = False,
          artigo: str = "", tipo: str = "texto",
          ajuda: str = "") -> dict:
    return {"nome": nome, "rotulo": rotulo, "de_onde": de_onde,
            "exigido": exigido, "artigo": artigo, "tipo": tipo,
            "ajuda": ajuda}


# **QUEM ASSINA NAO E CLARO DE FORMULARIO, E ESSA E A LISTA.**
#
#   Relato #65 do oficial, 15/09/2026: «nao faz sentido escolher quem assinou
#   [no termo]». E o #63 e a mesma coisa pelo lado do estrago: o assento 8266
#   foi lavrado com o campo de quem assina **em branco**, e o texto que foi para
#   o Livro diz
#
#       «...o(a) declarante assina. Eu, ____________, Oficial, dou fe, e
#        assino.»
#
#   — o nome de quem assina nao esta la, e «Oficial» ficou no lugar da funcao
#   real de quem assinou.
#
#   Os dois claros ficam nesta lista porque a resposta nao e do balcao: e a
#   **regra viva de quem responde pela serventia**, a mesma do cartao de
#   assinatura e da certidao do RI (`rc_termo._quem_assina`). Escolher na tela
#   permitiria ao escrevente por o nome de outro no papel — e o Livro do
#   Registro Civil e o papel que o declarante assina embaixo.
#
#   **E ELES CONTINUAM NO MODELO.** Tirar o claro do texto tiraria a assinatura
#   do termo; o que muda e de onde o valor vem.
QUEM_ASSINA_VEM_DE_FORA = ("escrevente", "funcao_do_escrevente")

# **O TRACO E UM SO, E MORA AQUI.** Ele e escrito no texto por
# `montar_do_formulario` e procurado por `rc_termo.completar_quem_assina`, que
# conserta o teor que chegou sem o nome de quem assina. Duas constantes com o
# mesmo desenho divergiriam no primeiro ajuste — e o conserto passaria a nao
# achar o traco, **calado**, porque `str.replace` que nao acha nao estoura.
O_TRACO_DA_CASA = "____________"

# **QUEM PASSA `quem_assina` E UMA TELA SO: O «VER COMO FICA» DO MODELO.**
#
#   Nas quatro pontes (`montar_*_do_assento`) o valor ja vem dentro de `valores`,
#   porque `rc_termo.montar` poe `escrevente` e `funcao_do_escrevente` la. Passar
#   de novo por parametro seria escrever duas vezes a mesma coisa — e um
#   parametro que nao muda nada se le como se mudasse.
#
#   No formulario do modelo (`/rcpn/formulario/<chave>`) os claros **sao campos
#   de texto**, e quem os le e `request.values`: ali a sobreposicao e o que
#   impede a previa de sair com o traco na assinatura. **Foi de uma previa assim
#   que o traco foi copiado para o teor** — o #63, medido em 625 assentos.


# ------------------------------------------------------------------ NASCIMENTO
#
# O TEXTO E O DO TERMO 8.369, palavra por palavra no que e impresso. As frases
# entre `{}` sao os claros que o escrevente preenchia a mao.
#
# **DUAS FRASES DELE CONFIRMAM O QUE SE CONSTRUIU EM 29 E 30/08:**
#   «nao e gemeo unico com este nome e 1o na ordem de filiacao» — o art. 234, que
#   manda a ordem de nascimento constar no assento de cada um;
#   «A genitora na ocasiao do parto contava 29 anos de idade» — a idade da mae no
#   parto, que NAO se calcula e se guarda como o declarante informou.
TERMO_NASCIMENTO = """\
Aos {data_do_ato}, neste Município de {cidade_do_ato}, Estado do \
{estado_do_ato}, neste ofício, compareceu {declarante_qualificacao}\
{frase_dnv}, e declarou que no dia {data_do_fato}{frase_hora}, em \
{local_do_fato}, nasceu uma criança do sexo {sexo}{frase_cor}, que recebeu o \
nome de: "{nome}"{frase_gemeos}, sendo filho de {filiacao1_qualificacao}\
{frase_filiacao2}{frase_idade_da_genitora}{frase_avos}\
{frase_naturalidade}{frase_primeiro_registro}{frase_cpf} Lido e achado conforme, o(a) declarante \
assina. Eu, {escrevente}, {funcao_do_escrevente}, dou fé e assino. \
{frase_matricula} {cidade_do_ato}/{uf_do_ato}, {data_do_ato}."""

CAMPOS_NASCIMENTO: tuple[dict, ...] = (
    campo("data_do_ato", "Data do registro",
          de_onde="calculada da data do ato", exigido=True,
          artigo="art. 233, I; forma do art. 795, § 4º",
          ajuda="por extenso **com o algarismo entre parênteses** no dia e no "
                "ano; o mês só por extenso — «dezenove (19) de agosto de dois "
                "mil e vinte e seis (2026)»"),
    campo("cidade_do_ato", "Município", de_onde="a serventia", exigido=True),
    campo("estado_do_ato", "Estado", de_onde="a serventia", exigido=True),
    campo("uf_do_ato", "UF", de_onde="a serventia", exigido=True),
    campo("declarante_qualificacao", "Declarante — qualificação inteira",
          de_onde="a pessoa de papel DECLARANTE", exigido=True,
          artigo="art. 54 da Lei nº 6.015/1973",
          ajuda="nome, nacionalidade, profissão, RG, **CPF**, naturalidade e "
                "residência — é assim que o termo desta casa o escreve"),
    campo("frase_dnv", "A DNV apresentada",
          de_onde="`dnv` do assento",
          ajuda="«apresentou a DNV n.º ...» — **sai inteira** quando não há"),
    campo("data_do_fato", "Data do nascimento", exigido=True,
          artigo="art. 233, I",
          ajuda="por extenso com algarismos, e depois em números — «oito (08) "
                "de agosto de dois mil e vinte e seis (2026) - 08/08/2026»"),
    campo("frase_hora", "Hora do nascimento",
          de_onde="montada de `hora_fato`", artigo="art. 233, I",
          ajuda="«a hora certa, sendo possível determiná-la ou aproximá-la». "
                "**Sai inteira** quando não se sabe"),
    campo("local_do_fato", "Local do nascimento", exigido=True,
          artigo="art. 233, I",
          ajuda="o nome do lugar **e o endereço**, com a cidade e a UF"),
    campo("sexo", "Sexo", exigido=True, artigo="art. 233, II", tipo="sexo"),
    campo("frase_cor", "Cor ou raça", de_onde="`cor_raca` do assento",
          ajuda="«, cor Parda» — **sai inteira** quando não informada"),
    campo("nome", "Nome do registrando", exigido=True, artigo="art. 233, IV",
          ajuda="vai **entre aspas** no termo"),
    campo("frase_gemeos", "Gêmeos — ordem de nascimento",
          de_onde="`gemeo_ordem` do assento", artigo="arts. 233, III e 234",
          ajuda="**quando não for gêmeo, não há menção nem espaço** — ordem do "
                "oficial em 30/08/2026"),
    campo("filiacao1_qualificacao", "Filiação 1 (mãe) — qualificação inteira",
          exigido=True, artigo="art. 233, VI",
          ajuda="nome, nacionalidade, profissão, RG, CPF, naturalidade, data "
                "de nascimento e residência"),
    campo("frase_filiacao2", "Filiação 2 (pai) — qualificação inteira",
          artigo="art. 233, VII",
          ajuda="**leva consigo o «, e de»**: sem isso, a ausência deixaria "
                "«sendo filho de X, e de.» — conjunção sem sujeito num livro "
                "que não aceita rasura"),
    campo("frase_idade_da_genitora", "Idade da genitora no parto",
          de_onde="**o que o declarante informou**, e não calculado",
          artigo="art. 233, VI",
          ajuda="«, tendo a mãe, na ocasião do parto, 24 anos de idade»"),
    campo("frase_avos", "Avós",
          de_onde="os quatro progenitores", artigo="art. 233, VIII",
          ajuda="«, tendo como avós (da filiação 1): X e Y e (da filiação 2): "
                "Z e W» — a forma que o oficial aprovou em 30/08/2026"),
    campo("frase_naturalidade", "Naturalidade declarada",
          de_onde="`naturalidade_declarada` do assento",
          artigo="art. 54, § 4º, da Lei nº 6.015/1973",
          ajuda="«A naturalidade declarada é de X, na forma do art. 54, § 4º, "
                "da Lei Federal n.º 6.015/1973.»"),
    campo("frase_primeiro_registro", "Primeiro registro",
          de_onde="todo nascimento lavrado nesta casa (nao sai no acervo)",
          ajuda="«Trata-se de primeiro registro.» - pedido do oficial em "
                "09/10/2026, junto com o CPF dentro do teor (sem averbacao)"),
    campo("frase_cpf", "CPF do registrado",
          de_onde="o CPF gerado no registro", artigo="art. 347",
          ajuda="«Inscrito no CPF n.º ...» — **o oficial pediu em 30/08/2026: "
                "«CPF é importante no termo»**. Sai inteira quando não houver"),
    campo("frase_matricula", "A matrícula de 32 dígitos",
          de_onde="composta ao lavrar", exigido=True,
          ajuda="«Matrícula 000000 01 55 2026 1 00024 169 0019555 53.» — vai "
                "**no fecho do termo**, como no termo real desta casa"),
    campo("escrevente", "Quem escreveu", exigido=True),
    campo("funcao_do_escrevente", "Em que qualidade", exigido=True,
          ajuda="«ESCREVENTE AUTORIZADA», «OFICIAL» — quem assina por "
                "delegação tem de dizer em que qualidade o faz"),
)


# ------------------------------------------------------------------- CASAMENTO
#
# O TERMO 8.369 E DE NASCIMENTO, e por isso o texto do casamento **nao vem
# medido de um papel desta casa**: ele se monta dos requisitos do art. 70 da Lei
# 6.015/1973 e do que o Codigo de Normas exige. Isso esta declarado no campo
# `medido` de cada modelo — nao se apresenta como precedente o que nao e.
TERMO_CASAMENTO = """\
Em {data_ato_extenso}, nesta cidade de {cidade_do_ato}, em cartório, perante mim e as \
testemunhas adiante nomeadas e no fim assinadas, compareceram os nubentes \
{nubente1_qualificacao} e {nubente2_qualificacao}, a fim de contrair \
matrimônio, apresentando {documentos_apresentados}{frase_habilitacao} \
E, não havendo impedimento, foram declarados casados sob o regime de \
{regime_bens}. \
{frase_dos_nomes} \
São pais do primeiro nubente {filiacao1}; e do segundo, {filiacao2}. \
{frase_conversao} \
Nada mais. Lido e achado conforme, assinam comigo, que escrevi, os nubentes e \
as testemunhas {testemunhas}. \
Eu, {escrevente}, {funcao_do_escrevente}, escrevi e assino."""

CAMPOS_CASAMENTO: tuple[dict, ...] = (
    campo("data_ato_extenso", "Data do registro, por extenso", exigido=True),
    campo("cidade_do_ato", "Cidade e comarca", exigido=True),
    campo("nubente1_qualificacao", "Primeiro nubente — qualificação",
          exigido=True, artigo="art. 70 da Lei nº 6.015/1973, item 1"),
    campo("nubente2_qualificacao", "Segundo nubente — qualificação",
          exigido=True, artigo="art. 70 da Lei nº 6.015/1973, item 1"),
    campo("frase_habilitacao", "Habilitação",
          de_onde="o processo de habilitação, quando é desta casa",
          ajuda="quando vier de outra serventia, o assento **compra selo "
                "próprio** — item 14.1.6"),
    campo("regime_bens", "Regime de bens", exigido=True,
          artigo="art. 70 da Lei nº 6.015/1973, item 6",
          ajuda="é campo obrigatório da certidão, e pode mudar entre a "
                "habilitação e a celebração"),
    # A RELACAO DOS DOCUMENTOS — pedido do oficial em 30/08/2026: «no
    # casamento, apresentar relacao dos documentos apresentados no termo».
    #
    #   Ate aqui o termo dizia «apresentando os documentos exigidos em lei»,
    #   generico. **Quem confere um casamento anos depois precisa saber QUAIS**
    #   — e a lista ja estava guardada em `hc_documentos`, com codigo,
    #   descricao e fundamento de cada um: o dado existia e nenhuma tela o
    #   levava ao papel.
    campo("documentos_apresentados", "Relação dos documentos apresentados",
          exigido=True, de_onde="a habilitação, quando é desta casa",
          artigo="art. 70 da Lei nº 6.015/1973",
          ajuda="**relacionados um a um**, e não «os documentos exigidos em "
                "lei» — quem confere anos depois precisa saber quais"),
    # A FRASE DOS NOMES — o outro pedido do mesmo dia: «se ninguem mudou o
    # nome, fala que ambos mantem os mesmos nomes».
    #
    #   A frase antiga afirmava sempre «Passou o conjuge X a assinar-se Y», e
    #   com ninguem mudando ela saia com o claro no meio de uma afirmacao. **O
    #   nome que cada um passa a usar e o motivo pelo qual a certidao de
    #   casamento existe**; nao dizer nada sobre ele e pior que dizer que nao
    #   mudou. Medido: o segundo conjuge muda em 17 dos 20 casamentos.
    campo("frase_dos_nomes", "O que aconteceu com os nomes", exigido=True,
          ajuda="ou quem passou a assinar-se como, ou que **ambos mantiveram "
                "os que tinham** — nunca o silêncio"),
    campo("filiacao1", "Filiação do primeiro nubente", exigido=True),
    campo("filiacao2", "Filiação do segundo nubente", exigido=True,
          ajuda="são **quatro** filiações no casamento, e o sistema lia duas"),
    campo("frase_conversao", "Conversão de união estável",
          ajuda="tem caminho e schema próprios no selador, e o número do "
                "processo da união estável é obrigatório"),
    campo("testemunhas", "Testemunhas", exigido=True),
    campo("escrevente", "Quem escreveu", exigido=True),
    campo("funcao_do_escrevente", "Em que qualidade", exigido=True),
)


# ----------------------------------------------------------------------- ÓBITO
# O TERMO DE OBITO — CONSTRUIDO DOS DOZE INCISOS DO ART. 255.
#
#   Lido no Codigo de Normas do TJMA, que repete o art. 80 da Lei 6.015/1973.
#   Cada frase abaixo responde a um inciso, e os que faltarem viram a
#   **declaracao do § 1º** — que e a parte mais interessante da norma:
#
#       «O oficial indagara, obrigatoriamente, a respeito de todos os itens
#        acima e, se nao for possivel constar do assento de obito todos os
#        elementos indicados, o oficial **declarara, no corpo do registro, que
#        fez a pergunta e que o declarante ignorava** os dados faltantes.»
#
#   Isto e o contrario de deixar campo em branco: a norma manda **escrever no
#   termo que se perguntou**. E exatamente a diferenca entre «nao» e «nao
#   perguntei» que `rc_marcas_do_obito` guarda — e ela tem base normativa, e
#   nao foi escolha de desenho.
#
#   O § 2º acrescenta que «a ausencia das informacoes nao obstara o registro»:
#   o termo sai mesmo incompleto, **com a declaracao dizendo o que faltou**.
TERMO_OBITO = """\
Em {data_ato_extenso}, nesta cidade de {cidade_do_ato}, em cartório, compareceu \
{declarante_qualificacao}, e declarou que, no dia {data_fato_extenso}\
{frase_hora}, em {local_do_fato}, faleceu {falecido_qualificacao}. \
{frase_filiacao} {frase_estado_civil} {frase_causa} {frase_sepultamento} \
{frase_eleitor} {frase_testamento} {frase_filhos} {frase_deixou_bens} \
{frase_identificacao} \
{frase_declaracao_de_obito} \
{frase_ignorados} \
Nada mais declarou. Lido e achado conforme, assina comigo, que escrevi. \
Eu, {escrevente}, {funcao_do_escrevente}, escrevi e assino."""

CAMPOS_OBITO: tuple[dict, ...] = (
    campo("data_ato_extenso", "Data do registro, por extenso", exigido=True),
    campo("cidade_do_ato", "Cidade e comarca", exigido=True),
    campo("declarante_qualificacao", "Declarante — qualificação", exigido=True,
          artigo="art. 256 — quem é obrigado a declarar",
          ajuda="cinco casos, do cônjuge à autoridade policial; e pode ser por "
                "procuração com firma reconhecida"),
    campo("data_fato_extenso", "Data do falecimento, por extenso", exigido=True,
          artigo="art. 255, I"),
    campo("frase_hora", "Hora do falecimento",
          de_onde="montada de `hora_fato` do assento", artigo="art. 255, I",
          ajuda="«aba hora, **se possível**» — e onde não se sabe a frase "
                "inteira sai do termo"),
    campo("local_do_fato", "Lugar do falecimento", exigido=True,
          artigo="art. 255, II",
          ajuda="«com indicação **precisa**» — a norma usa essa palavra"),
    campo("falecido_qualificacao", "Falecido — qualificação inteira",
          exigido=True, artigo="art. 255, III",
          ajuda="nome, sexo, idade, data de nascimento, cor, estado civil, "
                "profissão, naturalidade, domicílio e residência"),
    campo("frase_filiacao", "Filiação do falecido", artigo="art. 255, VI",
          ajuda="«os nomes, profissões, naturalidade e residência dos pais»"),
    campo("frase_estado_civil", "Cônjuge sobrevivente ou pré-morto",
          artigo="art. 255, IV",
          ajuda="se casado, o nome do sobrevivente **mesmo separado ou "
                "divorciado**; se viúvo, o do pré-morto — e o cartório do "
                "casamento nos dois casos"),
    campo("frase_causa", "Se a morte foi natural ou violenta, e a causa",
          artigo="art. 255, IX",
          ajuda="«com o nome dos atestantes». A **natureza** vai ao IBGE e à "
                "CRC com vocabulários diferentes"),
    campo("frase_sepultamento", "Lugar do sepultamento", artigo="art. 255, X"),
    campo("frase_eleitor", "Se era eleitor", artigo="art. 255, V",
          ajuda="é o que faz nascer a comunicação à Justiça Eleitoral"),
    campo("frase_testamento", "Se faleceu com testamento conhecido",
          artigo="art. 255, VII"),
    campo("frase_filhos", "Se deixou filhos, o nome e a idade de cada um",
          artigo="art. 255, VIII"),
    campo("frase_deixou_bens", "Se deixou bens e herdeiros menores ou interditados",
          artigo="art. 255, XI"),
    # **A EXIGENCIA E DE QUE O FALECIDO ESTEJA IDENTIFICADO**, e nao de que
    # esta frase exista: `qualificacao_inteira` ja traz o documento quando ha,
    # e esta frase so entra quando ele falta ou quando nao foi possivel
    # identificar. Marca-la como exigida fazia o termo repetir a identificacao
    # duas vezes — medido no primeiro ensaio, em 31/08/2026.
    campo("frase_identificacao", "Ao menos uma identificação do falecido",
          artigo="art. 255, XII",
          ajuda="PIS/PASEP, INSS, benefício, CPF, RG com órgão emissor, título "
                "de eleitor, registro de nascimento (livro, folha e termo) ou "
                "CTPS — **pelo menos uma**"),
    campo("frase_declaracao_de_obito", "A Declaração de Óbito", exigido=True,
          artigo="art. 254; e decisão desta casa em 30/08/2026",
          ajuda="**esta casa exige a DO em todo caso**, o que é mais estrito "
                "que o art. 254, que admitiria duas pessoas qualificadas onde "
                "não houvesse médico"),
    campo("frase_ignorados", "O que o declarante ignorava",
          artigo="art. 255, § 1º",
          de_onde="montada do que ficou **por perguntar** ou sem resposta",
          ajuda="a norma manda o oficial **declarar no corpo do registro que "
                "fez a pergunta e que o declarante ignorava** os dados que "
                "faltam — e o § 2º diz que a ausência não obsta o registro"),
    campo("escrevente", "Quem escreveu", exigido=True),
    campo("funcao_do_escrevente", "Em que qualidade", exigido=True),
)



# -------------------------------------------------------------------- LIVRO E
#
# **UM ESQUELETO SÓ PARA AS ESPÉCIES DO LIVRO E.** Ordem do oficial em
# 07/09/2026: «livro e usa o mesmo modelo» — ausência, interdição, tutela,
# emancipação, união estável, opção de nacionalidade e «outro» compartilham
# o mesmo corpo; o cabeçalho da folha (Termo|Livro|Folha) já é o de
# `rc_folha.COLUNAS`, e o título do ato sai de `rc_cabecalho.TITULO_DO_ATO`.
#
# **NÃO É PROSA ESPECÍFICA DE CADA ATO.** A casa edita o texto em
# `modelos_da_casa` (chave `RC_TERMO_LIVRO_E`) quando precisar afinar.
#
# **E O MESMO ESQUELETO PASSOU A DIZER O QUE A LEI MANDA — 13/10/2026.** Ordem
# do oficial: «preparemos o ambiente para viabilizar o próximo registro e todos
# os modelos, nos moldes da casa». Até aqui o termo dizia «lavrou-se o registro
# referente a Fulano» e mais nada: sem a sentença, sem o curador, sem os
# companheiros. **O modelo continua UM SÓ** (a ordem de 07/09 vale), e o que
# muda por espécie é uma FRASE INTEIRA montada pelo módulo — `frase_da_especie`
# —, a mesma forma do termo de nascimento: a decisão de a frase existir é do
# módulo, e não do modelo. Os requisitos de cada uma estão em
# `frase_do_livro_e`, com o artigo ao lado.
TERMO_LIVRO_E = """\
Aos {data_do_ato}, neste Município de {cidade_do_ato}, Estado do \
{estado_do_ato}, neste ofício, lavrou-se o {titulo_do_ato} referente a \
"{nome}"{qualificacao_do_titular}.{frase_da_especie}{frase_observacoes} Lido \
e achado conforme. Eu, {escrevente}, {funcao_do_escrevente}, dou fé e \
assino. {cidade_do_ato}/{uf_do_ato}, {data_do_ato}."""

CAMPOS_LIVRO_E: tuple[dict, ...] = (
    campo("data_do_ato", "Data do registro",
          de_onde="calculada da data do ato", exigido=True,
          ajuda="por extenso com o algarismo entre parênteses"),
    campo("cidade_do_ato", "Município", de_onde="a serventia", exigido=True),
    campo("estado_do_ato", "Estado", de_onde="a serventia", exigido=True),
    campo("uf_do_ato", "UF", de_onde="a serventia", exigido=True),
    campo("titulo_do_ato", "Título do ato",
          de_onde="`rc_cabecalho.TITULO_DO_ATO` pela espécie", exigido=True,
          ajuda="REGISTRO DE INTERDIÇÃO, REGISTRO DE AUSÊNCIA, etc."),
    campo("nome", "Nome do registrado", exigido=True,
          ajuda="vai entre aspas no termo"),
    campo("qualificacao_do_titular", "Qualificação do titular",
          de_onde="a pessoa do registro (nacionalidade, profissão, documentos, "
                  "naturalidade, nascimento, residência)",
          ajuda="frase opcional — sai vazia na união estável, em que os dois "
                "companheiros vêm qualificados na frase da espécie"),
    campo("frase_da_especie", "O que a lei manda constar",
          de_onde="`frase_do_livro_e`, pela espécie: o título (sentença, "
                  "escritura ou termo), o curador, o tutor, os companheiros…",
          ajuda="frase inteira montada pelo sistema; **sai vazia** no «outro»"),
    campo("frase_observacoes", "Teor / observações",
          de_onde="texto livre do assento, quando houver",
          ajuda="frase inteira opcional — **sai vazia** quando não há"),
    campo("escrevente", "Quem escreveu", exigido=True),
    campo("funcao_do_escrevente", "Em que qualidade", exigido=True),
)


# ------------------------------------------------------------------- o catálogo
#
# **UM MODELO POR ATO**, e cada um diz se o texto foi MEDIDO num papel desta casa
# ou montado dos requisitos da norma. **Apresentar como precedente o que nao e
# precedente seria a «etiqueta que afirma medicao sem ter medido»** — o defeito
# que este projeto ja pagou uma vez.
MODELOS: tuple[dict, ...] = (
    {"chave": "NASCIMENTO", "nome": "Termo de nascimento",
     "livro": "A", "texto": TERMO_NASCIMENTO, "campos": CAMPOS_NASCIMENTO,
     "conferido_no_papel": True,
     "fonte": "construído dos requisitos do art. 233 do Código de Normas "
              "do TJMA; o termo nº 8.369 desta casa serviu de **conferência**, "
              "e não de fonte",
     "artigo": "art. 233 do Código de Normas do TJMA; art. 54 da Lei nº "
               "6.015/1973"},
    {"chave": "CASAMENTO", "nome": "Termo de casamento",
     "livro": "B", "texto": TERMO_CASAMENTO, "campos": CAMPOS_CASAMENTO,
     "conferido_no_papel": False,
     "fonte": "construído dos requisitos do art. 70 da Lei nº 6.015/1973 — "
              "**é assim que o oficial mandou**, em 30/08/2026: os modelos do "
              "E-Ofício não se usam, nem o papel",
     "artigo": "art. 70 da Lei nº 6.015/1973"},
    {"chave": "OBITO", "nome": "Termo de óbito",
     "livro": "C", "texto": TERMO_OBITO, "campos": CAMPOS_OBITO,
     "conferido_no_papel": False,
     "fonte": "construído dos doze incisos do art. 255 do Código de Normas "
              "do TJMA, que repete o art. 80 da Lei nº 6.015/1973 — **é assim "
              "que o oficial mandou**, em 30/08/2026",
     "artigo": "art. 80 da Lei nº 6.015/1973"},
    {"chave": "LIVRO_E", "nome": "Termo do Livro E",
     "livro": "E", "texto": TERMO_LIVRO_E, "campos": CAMPOS_LIVRO_E,
     "conferido_no_papel": False,
     "fonte": "esqueleto compartilhado das espécies do Livro E — ordem do "
              "oficial em 07/09/2026: «livro e usa o mesmo modelo»; editável "
              "em modelos_da_casa",
     "artigo": "art. 33, V, da Lei nº 6.015/1973"},
)

CHAVES = tuple(m["chave"] for m in MODELOS)


# ------------------------------------------------- OS TIPOS DE TEOR
#
# **UM ATO TEM VÁRIOS TEORES, E NÃO UM.** Aprendido nos prints do E-Ofício em
# 30/08/2026: a aba «Teor» da tela de lavratura não é um texto — é um combo
# chamado **Tipo de Teor** mais um botão. Os três modelos acima são o teor
# COMUM de cada ato; os demais existem no livro e ainda não têm texto aqui.
#
# ESTA TABELA DECLARA O QUE FALTA, EM VEZ DE FINGIR QUE NÃO EXISTE. Escrever
# agora um texto para cada um seria repetir o defeito que o oficial apontou em
# 30/08 — «gerando uma expectativa que não corresponde à realidade». Um teor
# inventado por mim entraria num livro assinado como se fosse precedente desta
# casa, e não é.
#
# Para preencher qualquer linha destas basta **um termo em papel** do tipo
# correspondente: foi assim que o de nascimento saiu (termo nº 8.369).
TIPOS_DE_TEOR: tuple[dict, ...] = (
    {"especie": "NASCIMENTO", "tipo": "COMUM", "chave": "NASCIMENTO",
     "nome": "Nascimento — teor comum",
     "quando": "o registro dentro do prazo do art. 50 da Lei nº 6.015/1973"},
    {"especie": "NASCIMENTO", "tipo": "TARDIO", "chave": "",
     "nome": "Nascimento — registro tardio",
     "quando": "fora do prazo legal — art. 249 do Código de Normas do TJMA",
     "porque_falta": "o modelo desta casa traz impressa a dispensa de "
                     "testemunhas do Provimento 28/2018, que **eu não li** — "
                     "medir o texto antes de saber se a dispensa vale seria "
                     "gravar a dúvida no livro"},
    {"especie": "NASCIMENTO", "tipo": "GEMEOS", "chave": "",
     "nome": "Nascimento — gêmeos",
     "quando": "parto múltiplo, com a ordem de nascimento — art. 234",
     "porque_falta": "o teor comum já traz a frase dos gêmeos medida no termo "
                     "8.369; falta ver se a casa usa termo próprio ou o comum"},
    {"especie": "NASCIMENTO", "tipo": "SEM_FILIACAO_PATERNA", "chave": "",
     "nome": "Nascimento — sem filiação paterna",
     "quando": "declaração só pela genitora — art. 59 da Lei nº 6.015/1973",
     "porque_falta": "não há termo desta casa digitalizado para medir"},
    {"especie": "CASAMENTO", "tipo": "COMUM", "chave": "CASAMENTO",
     "nome": "Casamento — teor comum",
     "quando": "o casamento civil — art. 70 da Lei nº 6.015/1973"},
    {"especie": "CASAMENTO", "tipo": "RELIGIOSO", "chave": "",
     "nome": "Casamento religioso com efeitos civis",
     "quando": "Livro B-Auxiliar — arts. 71 a 75 da Lei nº 6.015/1973",
     "porque_falta": "livro próprio (B-Auxiliar, tipo **3** na matrícula), e "
                     "esta casa não tem termo dele digitalizado"},
    {"especie": "CASAMENTO", "tipo": "CONVERSAO", "chave": "",
     "nome": "Conversão de união estável em casamento",
     "quando": "art. 1.726 do Código Civil",
     "porque_falta": "não há termo desta casa digitalizado para medir"},
    {"especie": "OBITO", "tipo": "COMUM", "chave": "OBITO",
     "nome": "Óbito — teor comum",
     "quando": "o óbito com o falecido identificado — art. 80 da Lei nº 6.015"},
    {"especie": "OBITO", "tipo": "DESCONHECIDO", "chave": "",
     "nome": "Óbito de pessoa não identificada",
     "quando": "o falecido desconhecido — a caixa «Desconhecido» do assento",
     "porque_falta": "não há termo desta casa digitalizado para medir"},
    {"especie": "NATIMORTO", "tipo": "COMUM", "chave": "",
     "nome": "Natimorto",
     "quando": "Livro C-Auxiliar — art. 53 da Lei nº 6.015/1973",
     "porque_falta": "livro próprio (C-Auxiliar, tipo **5** na matrícula), e "
                     "esta casa não tem termo dele digitalizado"},
    # **ESTA LINHA FALTAVA, E A CONTA ACUSAVA — 15/09/2026.**
    #
    #   O termo do Livro E nasceu em 07/09/2026 com um modelo só para as suas
    #   espécies («livro e usa o mesmo modelo», ordem do oficial), e entrou em
    #   `MODELOS` — mas **não entrou aqui**. O efeito era este: a tela dos
    #   teores contava **3** prontos onde o catálogo tinha **4**, e o Livro E
    #   não aparecia em lista nenhuma; `tipos_do_ato("LIVRO_E")` estourava, e a
    #   tela do formulário dele ficava sem a lista dos teores do mesmo ato.
    #
    #   **Quem achou foi o teste que compara as duas contas** — «todo modelo
    #   tem um teor» —, e não a releitura: o modelo estava certo e a lista de
    #   fora dele é que envelheceu. É o defeito do menu e do `TITULO_DA_CARGA`
    #   outra vez: **lista escrita à mão noutro lugar envelhece na tarde em que
    #   se escreve.**
    #
    #   `LIVRO_E` aqui é um agrupamento de livro, como `NATIMORTO` — e não uma
    #   espécie do assento: as espécies (ausência, interdição, tutela,
    #   emancipação, união estável, opção de nacionalidade e outro) apontam
    #   todas para o mesmo texto.
    {"especie": "LIVRO_E", "tipo": "COMUM", "chave": "LIVRO_E",
     "nome": "Livro E — teor comum",
     "quando": "ausência, interdição, tutela, emancipação, união estável, "
               "opção de nacionalidade e outros — **um modelo só**, ordem do "
               "oficial em 07/09/2026: «livro e usa o mesmo modelo»"},
)

ESPECIES = tuple(dict.fromkeys(t["especie"] for t in TIPOS_DE_TEOR))


def tipos_do_ato(especie: str) -> tuple[dict, ...]:
    """Os teores daquele ato — os que têm texto e os que não têm.

    **DEVOLVE OS DOIS.** Uma lista só com os prontos faria a tela dizer que o
    nascimento tem um teor, quando ele tem quatro e nós temos um. Quem abre a
    tela precisa saber o tamanho do que falta, e não só o do que há.
    """
    e = (especie or "").strip().upper()
    achados = tuple(t for t in TIPOS_DE_TEOR if t["especie"] == e)
    if not achados:
        raise ModeloError(
            f"Não conheço o ato «{especie}». Os que conheço: "
            + ", ".join(ESPECIES) + ".")
    return achados


def tem_texto(tipo: dict) -> bool:
    """Se aquele teor já pode ser montado. `chave` vazia quer dizer que não."""
    return bool(tipo.get("chave"))


def quantos_teores_faltam() -> dict:
    """A conta, para a tela não precisar fazê-la. **Nunca escrita à mão.**"""
    total = len(TIPOS_DE_TEOR)
    prontos = sum(1 for t in TIPOS_DE_TEOR if tem_texto(t))
    return {"total": total, "prontos": prontos, "faltam": total - prontos}


def modelo(chave: str) -> dict:
    for m in MODELOS:
        if m["chave"] == chave:
            return m
    raise ModeloError(f"Não há modelo de termo para «{chave}».")


def campos_do(chave: str) -> tuple[dict, ...]:
    """Os claros daquele modelo — e é daqui que o formulário se monta."""
    return modelo(chave)["campos"]


def claros_do_texto(texto: str) -> tuple[str, ...]:
    """Os `{campos}` que o texto usa, na ordem em que aparecem. Só lê."""
    import re
    vistos: list[str] = []
    for nome in re.findall(r"\{(\w+)\}", texto or ""):
        if nome not in vistos:
            vistos.append(nome)
    return tuple(vistos)


def conferir(chave: str) -> list[str]:
    """Se os claros do texto e a lista de campos batem. Só lê.

    **É O GUARDA QUE IMPEDE AS DUAS LISTAS DE DIVERGIREM.** Um claro no texto sem
    campo na lista sai como `{assim}` no papel assinado; um campo na lista sem
    claro no texto é uma pergunta que o formulário faz e que não vai a lugar
    nenhum. Os dois enganam quem preenche.
    """
    m = modelo(chave)
    no_texto = set(claros_do_texto(m["texto"]))
    na_lista = {c["nome"] for c in m["campos"]}
    faltas = []
    for nome in sorted(no_texto - na_lista):
        faltas.append(
            f"«{{{nome}}}» está no texto e não tem campo no formulário — sairia "
            f"assim mesmo no papel assinado")
    for nome in sorted(na_lista - no_texto):
        faltas.append(
            f"o campo «{nome}» está no formulário e não aparece no texto — é "
            f"pergunta que não vai a lugar nenhum")
    return faltas


def _texto(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _com_os_espacos_da_frase(v: Any) -> str:
    """O valor que entra no texto, **COM** o espaco das bordas. So calcula.

    **O ESPAÇO DA BORDA É DA FRASE, E NÃO SOBRA DE DIGITAÇÃO** — medido em
    15/09/2026, no termo do assento 8266 e em outros sessenta e um. As frases
    ocasionais do Registro Civil nascem com o espaco que as separa do que vem
    antes: `frase_cpf` e « Inscrito no CPF n.º …», `frase_naturalidade` e
    «. A naturalidade declarada e de …», `frase_hora` e «, as 14:30».

    E `_texto` faz `str.strip()`, de modo que o termo saia
    «…Lei Federal n.º 6.015/1973.Inscrito no CPF n.º …» — **a frase colada no
    ponto da anterior**, e isso ia assim para `rc_assentos.teor`, que e o
    proprio Livro do Registro Civil e o papel que o declarante assina.

    Quem separa o que e da frase do que e desleixo e `limpar`, que colapsa
    espaco duplo e tira espaco antes de pontuacao. Aqui basta **nao comecar
    tirando**: o que se normaliza e so o miolo, que e onde a digitacao deixa
    quebra de linha e espaco repetido.
    """
    import re
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v))


# ============================================ a conferencia do corpo escrito

# **UM MODELO DO FORMATO ANTIGO SAIRIA LITERAL NO PAPEL ASSINADO.**
#
#   Ate 31/08/2026 os tres termos do Registro Civil eram Jinja — `{{ a.nome }}`,
#   com laco e condicao. Eles passaram a ser `CHAVES` (`{nome}`, do
#   `str.format`), que e o formato do texto da casa. **O que o oficial tenha
#   editado antes continua gravado em `mo_modelos`**, e o `str.format` nao
#   entende `{{ a.nome }}`: ele nao estoura — devolve `{ a.nome }`, com uma
#   chave so, e **isso iria escrito no livro**.
#
#   Por isso a recusa e ANTES, e diz o que fazer. Medido em 31/08/2026 no banco
#   do servidor: `mo_modelos` tem **zero linhas**, de modo que hoje ninguem e
#   alcancado — mas quem editar amanha, sem esta guarda, seria.
#
#   E a mesma funcao serve a tela do catalogo: conferir e montar tem de usar a
#   MESMA regra, senao a tela aprova o que o papel nao sabe imprimir. E a licao
#   da `normalizar_nome`, pela terceira vez.
MARCA_DO_FORMATO_ANTIGO = ("{{", "{%")


def conferir_corpo(chave: str, texto: str) -> str:
    """O que ha de errado neste corpo, ou `""` se estiver bom. So calcula."""
    corpo = str(texto or "")
    if not corpo.strip():
        return "O modelo está vazio."

    for marca in MARCA_DO_FORMATO_ANTIGO:
        if marca in corpo:
            return (
                f"Este modelo está escrito no formato antigo (usa «{marca}»), e "
                "os termos do Registro Civil passaram a usar o formato da casa "
                "— «{nome}», com uma chave só. Do jeito que está, o claro sairia "
                "escrito assim mesmo no papel assinado. Apague o corpo para "
                "voltar ao padrão da casa e ajuste a partir dele.")

    # **`MODELOS` E UMA TUPLA, E EU A TRATEI COMO DICIONARIO.** `campos_do` e a
    # funcao da casa que responde a isto, e usa-la e melhor que reescrever a
    # busca: reescrita, ela divergiria no primeiro conserto.
    try:
        conhecidos = {c["nome"] for c in campos_do(chave)}
    except ModeloError:
        return ""
    try:
        import string
        pedidos = {n for _, n, _, _ in string.Formatter().parse(corpo) if n}
    except ValueError as erro:
        return f"O modelo tem um claro mal escrito: {erro}"

    faltam = sorted(n for n in pedidos if n.split(".")[0].split("[")[0]
                    not in conhecidos)
    if faltam:
        return ("O modelo pede claros que este termo não tem: "
                + ", ".join(f"«{{{n}}}»" for n in faltam)
                + ". Confira a lista de campos ao lado.")
    return ""


def montar_do_formulario(chave: str, valores: dict,
                         texto: str | None = None,
                         quem_assina: dict | None = None) -> dict:
    """Monta o texto do termo com o que o formulário trouxe. Só calcula.

    **CLARO EM BRANCO NÃO SOME: FICA MARCADO.** Um `{campo}` que ninguém
    preencheu sairia como chave literal no papel assinado; substituí-lo por vazio
    faria a frase perder o sentido sem dizer por quê. Ele vira `____________`,
    que é o que o livro de papel tem — e a tela lista quais são.

    **QUEM ASSINA NÃO SE DIGITA.** Nos dois claros de `QUEM_ASSINA_VEM_DE_FORA`,
    quando `quem_assina` é informado ele **vence o formulário**. É o que impede
    a prévia do modelo — a única tela em que a assinatura é campo de texto — de
    mostrar o traço na assinatura. **Foi de uma prévia assim que o traço foi
    copiado para o teor de 625 assentos**: relato #63 do oficial, 15/09/2026.

    **FALTA E «NÃO É O CASO» SÃO COISAS DIFERENTES**, e devolvem-se separadas:
    `em_branco` é o que **falta** (campo exigido vazio) e decide `completo`;
    `nao_e_o_caso` é a frase ocasional que simplesmente não se aplica a este
    ato. Até 31/08/2026 as duas caíam na mesma lista, e um óbito comum — sem
    testamento, sem bens, sem causa declarada — saía marcado INCOMPLETO com dez
    linhas de aviso. **Alarme que soa sempre é alarme que ninguém ouve.**

    Este módulo **não grava**: quem congela o termo é `rc_termo.congelar`, e ele
    o faz uma vez só.
    """
    m = modelo(chave)
    # **O CORPO PODE VIR DE FORA, e e assim que o oficial edita o termo.**
    #
    #   Sem isto, o texto seria sempre o do codigo — e o relato #28 («preciso
    #   ter controle geral sobre os modelos») nao alcancaria os tres papeis
    #   mais importantes do Registro Civil. Quem passa o corpo e
    #   `rc_termo.montar`, que o busca em `modelos_da_casa.corpo_de`: sem linha
    #   na tabela vem o padrao daqui, e com linha vem o que ele escreveu.
    corpo = texto if texto is not None else m["texto"]
    dados, em_branco, nao_e_o_caso = {}, [], []
    for c in m["campos"]:
        bruto = (valores or {}).get(c["nome"])
        # **A ASSINATURA NÃO SE DIGITA, E NÃO SE ESCOLHE.** Ver
        # `QUEM_ASSINA_VEM_DE_FORA`: quando a tela diz quem assina, é isso que
        # vale — ainda que o campo tenha vindo vazio, que foi o defeito do
        # assento 8266.
        if quem_assina is not None and c["nome"] in QUEM_ASSINA_VEM_DE_FORA:
            bruto = quem_assina.get(c["nome"])
        valor = _texto(bruto)
        if not valor:
            # **FALTA E «NAO E O CASO» SAO COISAS DIFERENTES**, e ate
            # 31/08/2026 as duas caiam na mesma lista — de modo que um obito
            # comum saia com dez «em branco» e marcado INCOMPLETO. Metade dos
            # campos do obito e frase ocasional.
            #
            #   O traco `____________` ja distinguia os dois casos duas linhas
            #   abaixo; a CONTA e que nao distinguia. O texto estava certo e o
            #   numero discordava dele.
            (em_branco if c.get("exigido") else nao_e_o_caso).append(
                c["rotulo"])
            # O TRACO E SO DO CAMPO EXIGIDO. **Campo opcional vazio SOME.**
            #
            #   Medido em 30/08/2026, montando o termo de um assento real: o
            #   `frase_gemeos` de quem não é gêmeo virou traço colado ao nome —
            #   «PAULO HENRIQUE BARROS ALMEIDA____________». Traço onde não há
            #   claro é pior que claro em branco: no livro ele parece erro de
            #   impressão, e o escrevente vai preencher alguma coisa ali.
            #
            #   O que é opcional é frase inteira que só existe em certo caso —
            #   os gêmeos, a idade da genitora, a conversão de união estável.
            #   Quando o caso não é aquele, a frase não falta: **ela não
            #   existe**, e o termo tem de ler-se inteiro sem ela.
            valor = O_TRACO_DA_CASA if c.get("exigido") else ""
        else:
            # **O ESPACO DAS BORDAS NAO SE PERDE.** `valor` acima so decidiu
            # que a frase EXISTE; quem entra no texto e o valor com os espacos
            # que ela carrega — ver `_com_os_espacos_da_frase`.
            valor = _com_os_espacos_da_frase(bruto)
        dados[c["nome"]] = valor
    try:
        montado = corpo.format(**dados)
    except KeyError as erro:
        raise ModeloError(
            f"O modelo usa o claro {erro}, que não tem campo no formulário. "
            "Ele sairia assim mesmo no papel assinado.") from erro
    # **«NAO CONTERA QUALQUER MENCAO OU ESPACO»** — ordem do oficial em
    # 30/08/2026, sobre os gemeos, e vale para toda frase ocasional. Fazer a
    # frase sumir nao basta: entre as vizinhas fica espaco duplo, e antes da
    # pontuacao fica espaco solto. No papel isso se le como falha de impressao.
    # `em_branco` continua sendo O QUE FALTA — e agora e so isso. Quem le a
    # chave nas telas passa a ver a lista curta e verdadeira, sem precisar
    # mudar nada.
    return {"texto": limpar(montado), "em_branco": em_branco,
            "nao_e_o_caso": nao_e_o_caso, "completo": not em_branco}


# ===================================================================
# O TERMO MONTADO DO ASSENTO — o elo que faltava
# ===================================================================


MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def por_extenso_com_algarismo(n: int, feminino: bool = False) -> str:
    """`19` -> `dezenove (19)`.

    **É A ORDEM DO TERMO DESTA CASA**, e é o contrário de
    `livro_nucleo.com_algarismos`, que escreve `19 (dezenove)`. As duas formas
    atendem o art. 795, § 4º — «por extenso com repetição em algarismos» —, e
    a que se usa aqui é a que está no papel que a casa assina.
    """
    from livro_nucleo import por_extenso
    return f"{por_extenso(int(n), feminino)} ({int(n)})"


def data_do_termo(iso: Any, *, com_numeros: bool = False) -> str:
    """`2026-08-19` -> `dezenove (19) de agosto de dois mil e vinte e seis
    (2026)`; com `com_numeros`, acrescenta ` - 19/08/2026`.

    **ESTILO «EXTENSO» — pedido autorizado no teste do cartório em 05/10/2026.**
    O dia e o ano por extenso COM o algarismo entre parênteses (art. 795, § 4º,
    do Código de Normas); o **mês SÓ por extenso**, sem o «(8)»/«(N)».

    Até 05/10/2026 o mês saía com o número - «agosto (8)». A troca vale só
    para termos lavrados daqui para a frente: o teor já gravado na lavratura
    (`rc_termo.congelar` -> `rc_assentos.teor`) não é remontado nem alterado.
    Backup da forma anterior: `rc_modelos_do_livro.py.bak_pre_data_extenso_20261005`.
    """
    texto = _texto(iso)[:10]
    partes = texto.split("-")
    if len(partes) != 3 or not all(x.isdigit() for x in partes):
        return texto
    ano, mes, dia = (int(x) for x in partes)
    if not 1 <= mes <= 12:
        return texto
    # O DIA SAI COM DOIS DIGITOS — «oito (08)» (medido no termo real nº
    # 19.555). O MES SAI SO POR EXTENSO — «agosto», sem «(8)» —: estilo
    # «extenso», pedido em 05/10/2026, vale para os termos lavrados daqui
    # para a frente.
    from livro_nucleo import por_extenso
    fora = (f"{por_extenso(dia)} ({dia:02d}) de {MESES[mes - 1]} "
            f"de {por_extenso_com_algarismo(ano)}")
    if com_numeros:
        fora += f" - {dia:02d}/{mes:02d}/{ano}"
    return fora


def nome_em_negrito(nome: str | None) -> str:
    """O nome do registrado no termo — sempre em negrito (oficial 07/09/2026).

    A folha renderiza `face.termo|safe`; sem `<strong>` o nome sai igual ao
    resto do parágrafo. Pais/declarante NÃO passam por aqui.
    """
    n = _texto(nome).strip()
    return f"<strong>{n}</strong>" if n else ""


def qualificacao_inteira(p: dict, *, feminino: bool | None = None, nome_negrito: bool = False) -> str:
    """A pessoa como o termo desta casa a escreve.

    Medido no termo nº 19.555: **nome, nacionalidade, profissão, RG, CPF,
    naturalidade, data de nascimento e residência** — nessa ordem, e com as
    palavras concordando em gênero («portador»/«portadora», «inscrito»/
    «inscrita», «residente e domiciliado»/«domiciliada»).

    **O QUE NÃO SE SABE NÃO APARECE, E NÃO DEIXA VÍRGULA SOLTA.** «Fulano, ,
    portador do RG n.º ,» é pior que «Fulano»: parece erro de impressão num
    livro que não aceita rasura.
    """
    if not p:
        return ""
    f = (feminino if feminino is not None
         else _texto(p.get("sexo")).upper().startswith("F"))
    nome = _texto(p.get("nome")).strip()
    if nome_negrito and nome:
        nome = nome_em_negrito(nome)
    partes = [nome]
    for chave in ("nacionalidade", "profissao"):
        v = _texto(p.get(chave))
        if v:
            partes.append(v)
    rg = _texto(p.get("documento_numero")) if \
        _texto(p.get("documento_tipo")).upper() in ("RG", "") else ""
    if rg:
        partes.append(f"{'portadora' if f else 'portador'} do RG n.º {rg}")
    cpf = _texto(p.get("cpf")) or (
        _texto(p.get("documento_numero"))
        if _texto(p.get("documento_tipo")).upper() == "CPF" else "")
    if cpf:
        partes.append(f"{'inscrita' if f else 'inscrito'} no CPF n.º {cpf}")
    nat = _texto(p.get("naturalidade_cidade"))
    if nat:
        uf = _texto(p.get("naturalidade_uf"))
        partes.append(f"{'natural' if True else ''} de {nat}"
                      + (f"/{uf}" if uf else ""))
    nasc = _texto(p.get("data_nascimento"))[:10]
    if nasc and len(nasc) == 10:
        d, m, a = nasc[8:10], nasc[5:7], nasc[:4]
        partes.append(f"{'nascida' if f else 'nascido'} no dia {d}/{m}/{a}")
    end = _texto(p.get("endereco"))
    if end:
        pedaco = [end]
        for chave in ("bairro", "cidade"):
            v = _texto(p.get(chave))
            if v:
                pedaco.append(v)
        uf = _texto(p.get("uf"))
        residencia = ", ".join(pedaco) + (f"/{uf}" if uf else "")
        partes.append(f"residente e {'domiciliada' if f else 'domiciliado'} "
                      f"em {residencia}")
    return ", ".join(x for x in partes if x)


def _dois_nomes(a: dict, b: dict) -> str:
    """«FULANO e BELTRANA», ou só um deles, ou vazio.

    Escrever « e BELTRANA» quando o primeiro falta deixaria no livro uma
    conjunção sem sujeito.
    """
    nomes = [_texto((p or {}).get("nome")) for p in (a, b)]
    return " e ".join(n for n in nomes if n)


def limpar(texto: str) -> str:
    """Tira o que as frases ausentes deixam para trás.

    **«QUANDO NÃO FOR GÊMEO, NÃO CONTERÁ QUALQUER MENÇÃO OU ESPAÇO NO TERMO»**
    — ordem do oficial em 30/08/2026. Fazer a frase sumir não basta: entre as
    vizinhas fica um espaço duplo, e antes da pontuação fica um espaço solto.
    No papel isso se lê como falha de impressão.

    **NENHUMA QUEBRA DE LINHA SOBREVIVE** — «o corpo de todos os atos do
    cartório é texto corrido, sem espaços», ordem do oficial em 07/09/2026, e
    é a mesma regra do art. 795, § 2º do Código de Normas que
    `notas_modelos.py` já cumpria. Até essa data só a LINHA VAZIA (`\\n\\n+`)
    virava espaço; uma quebra ISOLADA sobrevivia inteira — e `TERMO_CASAMENTO`
    e `TERMO_OBITO` tinham seis e sete delas, por faltar o `\\` de
    continuação no código-fonte (`TERMO_NASCIMENTO`, ao lado, já não tinha
    nenhuma). Ela ia inteira para `rc_assentos.teor`, o próprio Livro do
    Registro Civil.
    """
    import re
    texto = re.sub(r"\s*\n\s*", " ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\s+([,.;:])", r"\1", texto)
    return texto.strip()


def valores_do_assento(assento: dict, pessoas: list[dict], *,
                       sv: dict | None = None,
                       frase_gemeos: str = "",
                       escrevente: str = "",
                       funcao_do_escrevente: str = "") -> dict:
    """Os claros do termo de nascimento, preenchidos do que o assento tem.

    **AS FRASES OCASIONAIS SAEM INTEIRAS, COM A PONTUAÇÃO.** Cada uma já vem
    com a vírgula que a precede, para que a ausência não deixe rastro — foi o
    que o oficial determinou sobre os gêmeos, e vale para todas.
    """
    por_papel: dict[str, dict] = {}
    for p in pessoas or []:
        por_papel.setdefault(_texto(p.get("papel")).upper(), p)

    registrado = por_papel.get("REGISTRADO", {})
    mae = por_papel.get("MAE", {})
    pai = por_papel.get("PAI", {})
    sv = sv or {}

    hora = _texto(assento.get("hora_fato"))
    h, _, m = hora.partition(":")
    idade = _texto(mae.get("idade_no_fato"))
    cor = _texto(assento.get("cor_raca")).capitalize()
    dnv = _texto(assento.get("dnv"))
    nat = _texto(assento.get("naturalidade_declarada"))
    cpf = _texto(assento.get("cpf_registrado")) or _texto(
        registrado.get("documento_numero")
        if _texto(registrado.get("documento_tipo")).upper() == "CPF" else "")
    matricula = _texto(assento.get("matricula"))

    local = _texto(assento.get("local_fato_nome"))
    endereco = _texto(assento.get("local_fato_endereco"))
    if local and endereco:
        local = f"{local}, {endereco}"

    avos1 = _dois_nomes(por_papel.get("AVO_MATERNO", {}),
                        por_papel.get("AVO_MATERNA", {}))
    avos2 = _dois_nomes(por_papel.get("AVO_PATERNO", {}),
                        por_papel.get("AVO_PATERNA", {}))
    if avos1 and avos2:
        frase_avos = (f", tendo como avós (da filiação 1): {avos1} e "
                      f"(da filiação 2): {avos2}")
    elif avos1 or avos2:
        qual = "1" if avos1 else "2"
        frase_avos = f", tendo como avós (da filiação {qual}): {avos1 or avos2}"
    else:
        frase_avos = ""

    return {
        "data_do_ato": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "estado_do_ato": _texto(sv.get("estado")) or "Maranhão",
        "uf_do_ato": _texto(sv.get("ri_uf")) or "MA",
        "declarante_qualificacao": qualificacao_inteira(
            por_papel.get("DECLARANTE", {})),
        "frase_dnv": f", apresentou a DNV n.º {dnv}" if dnv else "",
        "data_do_fato": data_do_termo(assento.get("data_fato"),
                                      com_numeros=True),
        "frase_hora": (f", às {h.strip()}:{m.strip()}"
                       if h.strip() and m.strip()
                       else (f", às {h.strip()} horas" if h.strip() else "")),
        "local_do_fato": local,
        "sexo": {"M": "Masculino", "F": "Feminino"}.get(
            _texto(registrado.get("sexo")).upper()[:1], ""),
        "frase_cor": f", cor {cor}" if cor else "",
        "nome": nome_em_negrito(assento.get("nome")),
        "frase_gemeos": frase_gemeos,
        # **O GENERO VEM DO SEXO DA PESSOA, E NAO DA POSICAO.** Forcei
        # feminino na filiacao 1 e o termo saiu «EVANDRO SOUSA SALES,
        # BRASILEIRO, LAVRADOR, INSCRITA no CPF, NASCIDA no dia...» —
        # medido num assento real em 30/08/2026. Ha assentos de casais do
        # mesmo sexo, e ha dado trocado no acervo: a posicao nao diz o
        # genero de ninguem.
        "filiacao1_qualificacao": qualificacao_inteira(mae),
        "frase_filiacao2": (f", e de {qualificacao_inteira(pai)}"
                            + frase_do_casamento_dos_pais(assento)
                            if qualificacao_inteira(pai) else ""),
        "frase_idade_da_genitora": (
            f", tendo a mãe, na ocasião do parto, {idade} anos de idade"
            if idade else ""),
        "frase_avos": frase_avos,
        "frase_naturalidade": (
            f". A naturalidade declarada é de {nat}, na forma do art. 54, "
            f"§ 4º, da Lei Federal n.º 6.015/1973." if nat else "."),
        # CPF E «PRIMEIRO REGISTRO» DENTRO DO TEOR - pedido do oficial em
        # 09/10/2026: o CPF entra no termo, sem averbacao. Concorda com o sexo
        # do registrado; sem CPF a frase some inteira (sem traco solto).
        "frase_primeiro_registro": (
            "" if (_texto(assento.get("origem")).upper() in ORIGENS_SEM_PRIMEIRO_REGISTRO
                   or _texto(assento.get("especie")).upper() == "NATIMORTO")
            else f" {FRASE_PRIMEIRO_REGISTRO}"),
        "frase_cpf": (f" {frase_do_cpf(cpf, registrado.get('sexo'))}"
                      if cpf else ""),
        # O ESPACO DEPOIS DO PONTO E PARTE DA FRASE. Sem ele sai
        # «...18.Cidade Exemplo/MA» — medido em 30/08/2026.
        "frase_matricula": f"Matrícula {matricula}." if matricula else "",
        "escrevente": escrevente,
        "funcao_do_escrevente": funcao_do_escrevente,
    }


def montar_do_assento(assento: dict, pessoas: list[dict],
                     texto: str | None = None, **kw) -> dict:
    """O termo de nascimento montado do assento. Só lê.

    Devolve o mesmo que `montar_do_formulario`: o texto, o que ficou em branco
    e se está completo — **e é de propósito que sejam a mesma forma**, para a
    tela mostrar os dois caminhos com o mesmo código.
    """
    valores = valores_do_assento(assento, pessoas, **kw)
    return montar_do_formulario("NASCIMENTO", valores, texto)


# ============================================================ CPF e 1o registro
#
# PEDIDO DO OFICIAL, 09/10/2026: «ADICIONAR O CPF SEM AVERBACAO E O PRIMEIRO
# REGISTRO» - dentro do teor do termo de nascimento. Vale so para o termo que
# se lavra daqui para a frente: o teor ja gravado (`rc_assentos.teor`) nao se
# remonta, e o do acervo (E-Oficio / digitado do livro antigo) nao ganha frase
# que o papel assinado nao tem.
FRASE_PRIMEIRO_REGISTRO = "Trata-se de primeiro registro."
ORIGENS_SEM_PRIMEIRO_REGISTRO = ("EOFICIO", "ACERVO")
ANCORA_DO_FECHO = "Lido e achado conforme"


def frase_do_cpf(cpf: Any, sexo: Any = "") -> str:
    """«Inscrito(a) no CPF n.º 000.000.000-00.» - vazio sem CPF. So calcula."""
    bruto = _texto(cpf)
    if not bruto:
        return ""
    n = "".join(ch for ch in bruto if ch.isdigit())
    if len(n) == 11:
        bruto = f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"
    quem = "Inscrita" if _texto(sexo).upper()[:1] == "F" else "Inscrito"
    return f"{quem} no CPF n.º {bruto}."


def completar_teor_nascimento(teor: Any, *, cpf: Any = "", sexo: Any = "") -> str:
    """Poe «primeiro registro» e o CPF no teor digitado, se faltarem. So calcula.

    O teor do balcao chega pronto (textarea / rascunho) e o CPF da conferencia
    so era gravado DEPOIS de lavrar - por isso o termo saia sem ele e o CPF ia
    por averbacao. Entra antes de «Lido e achado conforme»; sem essa ancora
    (texto proprio) nao adivinha o lugar e devolve o texto como veio.
    Idempotente: o que ja esta no texto nao entra de novo.
    """
    texto = _texto(teor)
    if not texto:
        return "" if teor is None else str(teor)
    i = texto.find(ANCORA_DO_FECHO)
    if i < 0:
        return texto
    faltam = []
    if "primeiro registro" not in texto.lower():
        faltam.append(FRASE_PRIMEIRO_REGISTRO)
    frase = frase_do_cpf(cpf, sexo)
    if frase:
        n = "".join(ch for ch in _texto(cpf) if ch.isdigit())
        formatado = frase.split("n.º ", 1)[1].rstrip(".")
        if formatado not in texto and (not n or n not in texto):
            faltam.append(frase)
    if not faltam:
        return texto
    antes = texto[:i].rstrip()
    if antes and antes[-1] not in ".!?":
        antes += "."
    return f"{antes} {' '.join(faltam)} {texto[i:]}"


# =========================================================================
# A PONTE DO CASAMENTO
# =========================================================================


def _lista_por_extenso(nomes: list) -> str:
    """«A, B e C» — a forma que um termo usa, e nao «A, B, C». So calcula."""
    limpos = [_texto(n) for n in nomes if _texto(n)]
    if not limpos:
        return ""
    if len(limpos) == 1:
        return limpos[0]
    return ", ".join(limpos[:-1]) + " e " + limpos[-1]


def frase_dos_nomes(nubente1: dict, nubente2: dict) -> str:
    """O que aconteceu com os nomes dos dois. So calcula.

    **PEDIDO DO OFICIAL, 30/08/2026**: «se ninguem mudou o nome, fala que ambos
    mantem os mesmos nomes».

    A frase antiga afirmava sempre «Passou o conjuge X a assinar-se Y», e com
    ninguem mudando ela saia com o claro no meio de uma afirmacao. **O silencio
    e pior que qualquer das duas frases**: o nome que cada um passa a usar e o
    motivo pelo qual a certidao de casamento existe.

    Medido: o segundo conjuge muda de nome em **17 dos 20** casamentos desta
    casa — de modo que o caso comum e mudar, e o incomum precisava de frase.
    """
    mudou = []
    for p in (nubente1 or {}, nubente2 or {}):
        antes, depois = _texto(p.get("nome")), _texto(p.get("nome_pos"))
        if depois and depois != antes:
            mudou.append((antes, depois))
    if not mudou:
        return ("Nenhum dos cônjuges alterou o nome, mantendo ambos os que "
                "já usavam.")
    if len(mudou) == 1:
        antes, depois = mudou[0]
        return f"Passou o cônjuge {antes} a assinar-se {depois}."
    return ("Passaram os cônjuges a assinar-se "
            + _lista_por_extenso([d for _, d in mudou]) + ", respectivamente.")


def relacao_de_documentos(documentos: list) -> str:
    """A relacao dos documentos apresentados, um a um. So calcula.

    **PEDIDO DO OFICIAL, 30/08/2026**: «no casamento, apresentar relacao dos
    documentos apresentados no termo».

    O termo dizia «apresentando os documentos exigidos em lei» — generico.
    **Quem confere um casamento anos depois precisa saber QUAIS**, e a lista ja
    estava guardada em `hc_documentos`: o dado existia e nenhuma tela o levava
    ao papel.

    **O DISPENSADO NAO ENTRA NA RELACAO DO APRESENTADO**, e nao some: ele sai
    numa frase propria, com o motivo. Misturar os dois faria o termo afirmar
    que se apresentou o que a serventia dispensou — e a dispensa e ato do
    oficial, que a correicao pergunta.
    """
    apresentados, dispensados = [], []
    for d in documentos or []:
        nome = _texto(d.get("descricao")) or _texto(d.get("codigo"))
        if not nome:
            continue
        # UMA LINHA POR NUBENTE, UM ITEM NO TERMO. `hc_documentos` guarda o
        # mesmo documento duas vezes (`de_quem` NUBENTE1 e NUBENTE2), e a
        # relacao saia «Certidao de nascimento..., Certidao de nascimento...»
        # — casamento 8366, 08/10/2026. O mesmo texto entra uma vez so.
        if d.get("dispensado"):
            motivo = _texto(d.get("dispensado_motivo"))
            item = f"{nome}{f' ({motivo})' if motivo else ''}"
            if item not in dispensados:
                dispensados.append(item)
        elif d.get("apresentado"):
            if nome not in apresentados:
                apresentados.append(nome)

    if not apresentados and not dispensados:
        return ""
    partes = []
    if apresentados:
        partes.append("os seguintes documentos: "
                      + _lista_por_extenso(apresentados))
    if dispensados:
        partes.append("dispensada a apresentação de "
                      + _lista_por_extenso(dispensados))
    return ", ".join(partes)


def regime_por_extenso(valor) -> str:
    """O regime de bens como o termo o escreve. So calcula.

    A tela de lavrar e a habilitacao gravam o CODIGO de `hc_schema.REGIMES`
    («COMUNHAO_PARCIAL»); o acervo gravou texto («COMUNHÃO PARCIAL DE BENS»).
    O codigo saia cru no termo — casamento 8366, 08/10/2026. Codigo conhecido
    vira o rotulo da casa, com inicial minuscula (vai no meio da frase); texto
    livre passa como veio.
    """
    bruto = _texto(valor)
    try:
        import hc_schema as HC
        rotulo = HC.REGIMES.get(bruto.upper())
    except Exception:                                        # noqa: BLE001
        rotulo = None
    if not rotulo:
        return bruto
    return rotulo[:1].lower() + rotulo[1:]


def valores_do_casamento(assento: dict, pessoas: list[dict], *,
                         documentos: list | None = None,
                         sv: dict | None = None,
                         escrevente: str = "",
                         funcao_do_escrevente: str = "") -> dict:
    """Os claros do termo de casamento, preenchidos do que o assento tem.

    **AS QUATRO FILIACOES SAO DUAS FRASES**, uma por nubente — e sao quatro
    pessoas: `PAI_NUBENTE1`, `MAE_NUBENTE1`, `PAI_NUBENTE2`, `MAE_NUBENTE2`.
    Ate 31/08/2026 a especie nao declarava esses papeis, e por isso **a tela de
    lavrar casamento nao oferecia filiacao nenhuma** — sendo que o art. 70 da
    Lei 6.015/1973 a exige.
    """
    por_papel: dict[str, dict] = {}
    testemunhas = []
    for p in pessoas or []:
        papel = _texto(p.get("papel")).upper()
        if papel == "TESTEMUNHA":
            testemunhas.append(_texto(p.get("nome")))
        else:
            por_papel.setdefault(papel, p)
    sv = sv or {}

    n1 = por_papel.get("NUBENTE1", {})
    n2 = por_papel.get("NUBENTE2", {})

    de_fora = _texto(assento.get("habilitacao_serventia"))
    proclamas = _data_br(assento.get("proclamas_data"))
    frase_habilitacao = (
        f" e a certidão de habilitação expedida por {de_fora}"
        + (f", com os proclamas publicados em {proclamas}" if proclamas else "")
        + "."
        if de_fora else ".")
    # A RELAÇÃO DOS DOCUMENTOS (art. 70, 5º): a da habilitação desta casa vem
    # de `hc_documentos`; a de fora, do que o balcão digitou (13/10/2026).
    docs_digitados = _texto(assento.get("documentos_apresentados"))
    relacao = relacao_de_documentos(documentos) or (
        f"os seguintes documentos: {docs_digitados}" if docs_digitados else "")

    processo = _texto(assento.get("uniao_estavel_processo"))
    frase_conversao = (
        f"Trata-se de conversão de união estável, processo n.º {processo}."
        if processo else "")

    return {
        "data_ato_extenso": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "nubente1_qualificacao": qualificacao_inteira(n1, nome_negrito=True)
                                 + frase_do_casamento_anterior(assento, "nubente1"),
        "nubente2_qualificacao": qualificacao_inteira(n2, nome_negrito=True)
                                 + frase_do_casamento_anterior(assento, "nubente2"),
        "documentos_apresentados": relacao,
        "frase_habilitacao": frase_habilitacao,
        "regime_bens": (regime_por_extenso(assento.get("regime_bens"))
                        + frase_do_pacto(assento)),
        "frase_dos_nomes": frase_dos_nomes(n1, n2),
        "filiacao1": _dois_nomes(por_papel.get("MAE_NUBENTE1", {}),
                                 por_papel.get("PAI_NUBENTE1", {})),
        "filiacao2": _dois_nomes(por_papel.get("MAE_NUBENTE2", {}),
                                 por_papel.get("PAI_NUBENTE2", {})),
        "frase_conversao": frase_conversao,
        "testemunhas": _lista_por_extenso(testemunhas),
        "escrevente": escrevente,
        "funcao_do_escrevente": funcao_do_escrevente,
    }


def montar_casamento_do_assento(assento: dict, pessoas: list[dict],
                                texto: str | None = None,
                                **kw) -> dict:
    """O termo de casamento montado do assento. So le."""
    valores = valores_do_casamento(assento, pessoas, **kw)
    return montar_do_formulario("CASAMENTO", valores, texto)


# =========================================================================
# A PONTE DO OBITO
# =========================================================================


def frase_dos_ignorados(marcas: dict) -> str:
    """A declaracao do art. 255, § 1o. So calcula.

    **A NORMA MANDA ESCREVER QUE SE PERGUNTOU**, e nao deixar o campo vazio: se
    nao for possivel constar todos os elementos, o oficial «declarara, no corpo
    do registro, que fez a pergunta e que o declarante ignorava» o que falta.

    Por isso `rc_marcas_do_obito` guarda **tres** estados e nao dois: «sim»,
    «nao» e **«nao perguntado»** — e sao os nao perguntados que entram nesta
    frase. Um campo vazio nao distingue «o falecido nao tinha bens» de «ninguem
    perguntou se tinha», e o termo tem de dizer qual dos dois foi.
    """
    import rc_marcas_do_obito as MO

    ignorados = []
    for m in MO.MARCAS:
        if _texto((marcas or {}).get(m["chave"])) == MO.NAO_PERGUNTADO:
            ignorados.append(_texto(m.get("no_termo")) or
                             _texto(m["rotulo"]).lower())
    if not ignorados:
        return ""
    return ("O oficial indagou a respeito de todos os itens do art. 255, e o "
            "declarante ignorava: " + _lista_por_extenso(ignorados)
            + ", na forma do § 1º do referido artigo.")


# ---------------------------------------------- o que a lei pede (13/10/2026)
#
# Frases dos campos que a tela passou a perguntar — todos opcionais: **sem
# dado, a frase some inteira**, e o termo fica como era.

def _data_br(iso: Any) -> str:
    """`2010-05-03` → `03/05/2010`; o que não for data passa como veio."""
    t = _texto(iso)
    if len(t) >= 10 and t[4] == "-" and t[7] == "-":
        return f"{t[8:10]}/{t[5:7]}/{t[:4]}"
    return t


def frase_do_conjuge_do_falecido(assento: dict, estado_civil: str) -> str:
    """Art. 80, 4º; CN art. 255, IV — o cônjuge sobrevivente (mesmo separado
    ou divorciado) ou o pré-morto, e o cartório do casamento. So calcula."""
    nome = _texto(assento.get("obito_conjuge_nome"))
    cartorio = _texto(assento.get("obito_conjuge_cartorio"))
    base = f"Era {estado_civil}" if estado_civil else ""
    if not nome:
        return f"{base}." if base else ""
    pre_morto = _texto(assento.get("obito_conjuge_situacao")).upper() == "PRE_MORTO"
    quem = "cônjuge pré-morto" if pre_morto else "cônjuge sobrevivente"
    frase = (f"{base}, sendo {quem} {nome}" if base else
             f"Deixou como {quem} {nome}" if not pre_morto else
             f"Teve como {quem} {nome}")
    if cartorio:
        frase += f", com casamento registrado em {cartorio}"
    return frase + "."


def frase_dos_filhos_do_falecido(assento: dict, marca_texto: str) -> str:
    """Art. 80, 7º; CN art. 255, VIII — se deixou filhos, o nome e a idade de
    cada um. A lista é texto livre, um por linha. So calcula."""
    linhas = [ln.strip(" ;,.") for ln in _texto(assento.get("obito_filhos")).splitlines()]
    linhas = [ln for ln in linhas if ln]
    if not linhas:
        return marca_texto
    return "Deixou os filhos: " + "; ".join(linhas) + "."


def frase_dos_herdeiros(assento: dict) -> str:
    """CN art. 255, XI — herdeiros menores ou interditados. So calcula."""
    v = _texto(assento.get("obito_herdeiros_menores")).upper()
    if v == "SIM":
        return " Deixou herdeiros menores ou interditados."
    if v == "NAO":
        return " Não deixou herdeiros menores nem interditados."
    return ""


def frase_do_casamento_anterior(assento: dict, qual: str) -> str:
    """Art. 70, 3º; CN art. 284, III — o cônjuge precedente e a data da
    dissolução, junto da qualificação do nubente. So calcula."""
    nome = _texto(assento.get(f"{qual}_conjuge_anterior"))
    if not nome:
        return ""
    data = _data_br(assento.get(f"{qual}_dissolucao_data"))
    return (f", tendo sido casado(a) com {nome}"
            + (f", casamento dissolvido em {data}" if data else ""))


def frase_do_pacto(assento: dict) -> str:
    """Art. 70, 7º; CN art. 284, VII — data e serventia da escritura de
    pacto antenupcial. So calcula."""
    data = _data_br(assento.get("pacto_data"))
    serventia = _texto(assento.get("pacto_serventia"))
    if not data and not serventia:
        return ""
    return (", conforme escritura de pacto antenupcial"
            + (f" lavrada em {data}" if data else "")
            + (f" nas notas de {serventia}" if serventia else ""))


def frase_do_casamento_dos_pais(assento: dict) -> str:
    """Art. 54, 7º — «lugar e cartório onde se casaram» os pais. So calcula."""
    lugar = _texto(assento.get("pais_casamento_lugar"))
    cartorio = _texto(assento.get("pais_casamento_cartorio"))
    if not lugar and not cartorio:
        return ""
    return (", casados entre si"
            + (f" em {lugar}" if lugar else "")
            + (f", com registro em {cartorio}" if cartorio else ""))


def valores_do_obito(assento: dict, pessoas: list[dict], *,
                     marcas: dict | None = None,
                     sv: dict | None = None,
                     escrevente: str = "",
                     funcao_do_escrevente: str = "") -> dict:
    """Os claros do termo de obito, preenchidos do que o assento tem."""
    import rc_marcas_do_obito as MO

    por_papel: dict[str, dict] = {}
    for p in pessoas or []:
        por_papel.setdefault(_texto(p.get("papel")).upper(), p)
    sv = sv or {}
    marcas = marcas or {}

    falecido = por_papel.get("FALECIDO", {})
    hora = _texto(assento.get("hora_fato"))
    h, _, mm = hora.partition(":")

    local = _texto(assento.get("local_fato_nome"))
    endereco = _texto(assento.get("local_fato_endereco"))
    if local and endereco:
        local = f"{local}, {endereco}"

    filiacao = _dois_nomes(por_papel.get("MAE", {}), por_papel.get("PAI", {}))
    estado_civil = _texto(falecido.get("estado_civil"))
    numero_do = _texto(assento.get("numero_do"))

    def _sim(chave: str) -> bool:
        return _texto(marcas.get(chave)) == MO.SIM

    def _nao(chave: str) -> bool:
        return _texto(marcas.get(chave)) == MO.NAO

    # AS TRES FRASES DAS MARCAS. **«Sim» e «nao» sao os dois que se escrevem**;
    # o «nao perguntado» nao vira frase aqui — ele vai para a declaracao do
    # § 1o, que e onde a norma manda que ele apareca.
    def _marca(chave: str, quando_sim: str, quando_nao: str) -> str:
        if _sim(chave):
            return quando_sim
        if _nao(chave):
            return quando_nao
        return ""

    return {
        "data_ato_extenso": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "declarante_qualificacao": qualificacao_inteira(
            por_papel.get("DECLARANTE", {})),
        "falecido_qualificacao": qualificacao_inteira(falecido, nome_negrito=True),
        "data_fato_extenso": data_do_termo(assento.get("data_fato"),
                                           com_numeros=True),
        "frase_hora": (f", às {h.strip()}:{mm.strip()}"
                       if h.strip() and mm.strip()
                       else (f", às {h.strip()} horas" if h.strip() else "")),
        "local_do_fato": local,
        # **AS FRASES SAO INTEIRAS, e comecam depois de um ponto.** O modelo
        # fecha a qualificacao com `.` e abre linha nova; uma frase que
        # comecasse com virgula sairia «lavrador., filho de» — medido no
        # primeiro ensaio desta ponte, em 31/08/2026.
        "frase_filiacao": f"Filho de {filiacao}." if filiacao else "",
        "frase_estado_civil": frase_do_conjuge_do_falecido(assento, estado_civil),
        # **A IDENTIFICACAO E O DOCUMENTO DO FALECIDO**, e nao o contrario —
        # eu inverti o sentido do campo no primeiro ensaio. O rotulo diz «ao
        # menos uma identificacao do falecido»: quando ha documento, ele vai
        # escrito; quando a pessoa nao foi identificada, e isso que se declara.
        # **ELA NAO REPETE O QUE A QUALIFICACAO JA DISSE.** No primeiro ensaio
        # o termo saia com «faleceu ANTONIO PEREIRA, lavrador, portador do RG
        # n.º 123456.» e, tres linhas abaixo, «Identificado por RG n.º
        # 123456.» — a mesma coisa duas vezes no papel que a serventia assina.
        #
        #   `qualificacao_inteira` ja traz o documento quando ha. O que a norma
        #   exige e que o falecido **esteja identificado**, e nao que exista uma
        #   frase com esse nome: ela so aparece quando a qualificacao nao
        #   identifica — ou quando nao foi possivel identificar ninguem, que e o
        #   caso em que a declaracao e obrigatoria.
        "frase_identificacao": (
            "Não foi possível identificar a pessoa falecida."
            if _sim("obito_desconhecido")
            else ("" if _texto(falecido.get("documento_numero"))
                  else "")),
        "frase_declaracao_de_obito": (
            f"Apresentada a Declaração de Óbito n.º {numero_do}."
            if numero_do else ""),
        "frase_causa": (
            f"A morte foi {_texto(assento.get('causa_morte'))}"
            + (f", atestada por {_texto(assento.get('atestante'))}"
               if _texto(assento.get("atestante")) else "")
            + (f", {_texto(assento.get('atestante_documento'))}"
               if _texto(assento.get("atestante_documento")) else "")
            + "."
            if _texto(assento.get("causa_morte")) else ""),
        "frase_sepultamento": (
            f"Sepultado em {_texto(assento.get('local_sepultamento'))}."
            if _texto(assento.get("local_sepultamento")) else ""),
        "frase_eleitor": _marca("obito_eleitor", "Era eleitor.",
                                "Não era eleitor."),
        "frase_deixou_bens": (_marca("obito_possui_bens", "Deixou bens.",
                                     "Não deixou bens.")
                              + frase_dos_herdeiros(assento)).strip(),
        "frase_filhos": (frase_dos_filhos_do_falecido(
                             assento, _marca("obito_possui_filho",
                                             "Deixou filhos.",
                                             "Não deixou filhos."))
                         if _sim("obito_possui_filho") else
                         _marca("obito_possui_filho", "Deixou filhos.",
                                "Não deixou filhos.")),
        "frase_testamento": (
            f"Deixou testamento conhecido: "
            f"{_texto(assento.get('testamento'))}."
            if _texto(assento.get("testamento")) else ""),
        "frase_ignorados": frase_dos_ignorados(marcas),
        "escrevente": escrevente,
        "funcao_do_escrevente": funcao_do_escrevente,
    }


def montar_obito_do_assento(assento: dict, pessoas: list[dict],
                     texto: str | None = None, **kw) -> dict:
    """O termo de obito montado do assento. So le."""
    valores = valores_do_obito(assento, pessoas, **kw)
    return montar_do_formulario("OBITO", valores, texto)


# =========================================================================
# A PONTE DO LIVRO E
# =========================================================================


def _feminino(p: dict | None) -> bool:
    return _texto((p or {}).get("sexo")).upper().startswith("F")


def _do_titulo(assento: dict) -> str:
    """«por sentença proferida em … pelo juízo …» — o título que se registra.
    So calcula. Sem título informado, devolve vazio: não se inventa sentença."""
    tipo = _texto(assento.get("livro_e_titulo")).upper()
    data = data_do_termo(assento.get("livro_e_titulo_data"))
    if tipo == "SENTENCA":
        juiz = _texto(assento.get("livro_e_juiz"))
        juizo = _texto(assento.get("livro_e_juizo"))
        processo = _texto(assento.get("livro_e_processo"))
        transito = data_do_termo(assento.get("livro_e_transito"))
        return ("por sentença proferida" + (f" em {data}" if data else "")
                + (f" pelo Juízo da {juizo}" if juizo else "")
                + ((f", MM. Juiz(a) {juiz}" if juizo else
                    f" pelo(a) MM. Juiz(a) {juiz}") if juiz else "")
                + (f", nos autos do processo n.º {processo}" if processo else "")
                + (f", transitada em julgado em {transito}" if transito else ""))
    if tipo == "ESCRITURA":
        livro = _texto(assento.get("livro_e_escritura_livro"))
        folha = _texto(assento.get("livro_e_escritura_folha"))
        tab = _texto(assento.get("livro_e_tabelionato"))
        return ("por escritura pública lavrada" + (f" em {data}" if data else "")
                + (f" no livro {livro}" if livro else "")
                + (f", folha {folha}" if folha else "")
                + (f", nas notas de {tab}" if tab else ""))
    if tipo == "TERMO":
        return ("por termo declaratório lavrado nesta serventia"
                + (f" em {data}" if data else ""))
    return ""


def _filiacao_curta(titular: dict | None, mae: dict | None,
                    pai: dict | None) -> str:
    """«, filho de X e de Y» — só os nomes (art. 94-A, III), na ordem da casa
    (a filiação 1 primeiro). So calcula."""
    nomes = [n for n in (_texto((mae or {}).get("nome")),
                         _texto((pai or {}).get("nome"))) if n]
    if not nomes:
        return ""
    return (f", {'filha' if _feminino(titular) else 'filho'} de "
            + " e de ".join(nomes))


def frase_do_livro_e(especie: str, assento: dict,
                     por_papel: dict[str, dict]) -> str:
    """O que a lei manda constar no registro do Livro E, por espécie. So
    calcula. **O que não se informou não aparece, e não deixa vírgula solta**
    — a mesma regra de `qualificacao_inteira`.

    EMANCIPAÇÃO, art. 90: data, o emancipado, o registro do nascimento, os
    pais ou o tutor. INTERDIÇÃO, art. 92: a sentença, o registro do
    nascimento e do casamento, o cônjuge, o curador, quem requereu e a causa,
    os limites, a internação. AUSÊNCIA, art. 94: o mesmo, mais o tempo de
    ausência e quem promoveu. TUTELA: a lei não lista; segue a interdição por
    analogia. UNIÃO ESTÁVEL, art. 94-A: os dois qualificados, os pais, os
    registros anteriores, o título, o regime e o nome que passam a usar.
    OPÇÃO DE NACIONALIDADE, art. 32, § 4º: a sentença da Justiça Federal.
    """
    a = assento or {}
    t = por_papel.get("REGISTRADO") or {}
    titulo = _do_titulo(a)
    pelo = f" {titulo}" if titulo else ""
    nasc = _texto(a.get("livro_e_registro_nascimento"))
    reg_nasc = f", com nascimento registrado em {nasc}" if nasc else ""
    cas = _texto(a.get("livro_e_registro_casamento"))
    conj = _texto(a.get("livro_e_conjuge"))
    reg_cas = (f", casado(a) com {conj}" if conj else "") + (
        f", com casamento registrado em {cas}" if cas else "")

    def q(papel: str) -> str:
        return qualificacao_inteira(por_papel.get(papel) or {})

    def nomeado(papel: str, masc: str, fem: str) -> str:
        p = por_papel.get(papel)
        if not p or not _texto(p.get("nome")):
            return ""
        return (f", sendo {'nomeada' if _feminino(p) else 'nomeado'} "
                f"{fem if _feminino(p) else masc} {q(papel)}")

    if especie == "EMANCIPACAO":
        tutor = por_papel.get("TUTOR")
        tutela = (f", representado(a) por seu(sua) tutor(a) {q('TUTOR')}"
                  if tutor and _texto(tutor.get("nome")) else "")
        return (f" Emancipação concedida{pelo}{reg_nasc}"
                f"{_filiacao_curta(t, por_papel.get('MAE'), por_papel.get('PAI'))}"
                f"{tutela}.")
    if especie == "INTERDICAO":
        causa = _texto(a.get("livro_e_causa"))
        limites = _texto(a.get("livro_e_limites"))
        intern = _texto(a.get("livro_e_internacao"))
        req = por_papel.get("REQUERENTE")
        return (f" Interdição decretada{pelo}{reg_nasc}{reg_cas}"
                + (f", a requerimento de {q('REQUERENTE')}"
                   if req and _texto(req.get("nome")) else "")
                + (f", tendo por causa {causa}" if causa else "")
                + nomeado("CURADOR", "curador", "curadora")
                + (f", nos seguintes limites da curatela: {limites}"
                   if limites else "") + "."
                + (f" Local de internação: {intern}." if intern else ""))
    if especie == "AUSENCIA":
        tempo = _texto(a.get("livro_e_ausencia_tempo"))
        limites = _texto(a.get("livro_e_limites"))
        req = por_papel.get("REQUERENTE")
        return (f" Ausência declarada{pelo}{reg_nasc}{reg_cas}"
                + (f", contando {tempo} de ausência até a data da sentença"
                   if tempo else "")
                + (f", em processo promovido por {q('REQUERENTE')}"
                   if req and _texto(req.get("nome")) else "")
                + nomeado("CURADOR", "curador", "curadora")
                + (f", nos seguintes limites da curatela: {limites}"
                   if limites else "") + ".")
    if especie == "TUTELA":
        return (f" Tutela deferida{pelo}{reg_nasc}"
                f"{_filiacao_curta(t, por_papel.get('MAE'), por_papel.get('PAI'))}"
                f"{nomeado('TUTOR', 'tutor', 'tutora')}.")
    if especie == "UNIAO_ESTAVEL":
        c1, c2 = por_papel.get("COMPANHEIRO1"), por_papel.get("COMPANHEIRO2")
        lados = []
        for c, mae, pai in ((c1, "MAE_COMPANHEIRO1", "PAI_COMPANHEIRO1"),
                            (c2, "MAE_COMPANHEIRO2", "PAI_COMPANHEIRO2")):
            if c and _texto(c.get("nome")):
                lados.append(qualificacao_inteira(c) + _filiacao_curta(
                    c, por_papel.get(mae), por_papel.get(pai)))
        inicio = data_do_termo(a.get("livro_e_uniao_inicio"))
        regime = regime_por_extenso(a.get("regime_bens"))
        frase = (" Fica registrada a união estável"
                 + (f" entre {', e '.join(lados)}" if lados else "")
                 + (f", reconhecida{pelo}" if titulo else "")
                 + (f", com início em {inicio}" if inicio else "")
                 + (f", sob o regime de {regime}" if regime else "") + ".")
        if nasc:
            frase += f" Registros de nascimento: {nasc}."
        if cas:
            frase += (" Casamentos e uniões estáveis anteriores, e óbitos de "
                      f"cônjuges ou companheiros: {cas}.")
        for c in (c1, c2):
            if c and _texto(c.get("nome_pos")) and \
                    _texto(c.get("nome_pos")) != _texto(c.get("nome")):
                frase += (f" {_texto(c.get('nome'))} passa a usar o nome "
                          f"{_texto(c.get('nome_pos'))}.")
        return frase
    if especie == "OPCAO_NACIONALIDADE":
        return (f" Opção pela nacionalidade brasileira homologada{pelo}"
                f"{reg_nasc}"
                f"{_filiacao_curta(t, por_papel.get('MAE'), por_papel.get('PAI'))}.")
    return ""


def valores_livro_e_do_assento(assento: dict, pessoas: list[dict], *,
                               sv: dict | None = None,
                               escrevente: str = "",
                               funcao_do_escrevente: str = "") -> dict:
    """Os claros do termo do Livro E, preenchidos do que o assento tem.

    **UM MODELO SÓ PARA AS SETE ESPÉCIES.** O título do ato muda; o corpo é o
    mesmo. O oficial edita o texto em `modelos_da_casa` se precisar afinar.
    """
    import rc_cabecalho as CAB

    por_papel: dict[str, dict] = {}
    for p in pessoas or []:
        por_papel.setdefault(_texto(p.get("papel")).upper(), p)
    sv = sv or {}

    registrado = por_papel.get("REGISTRADO", {})
    nome = (_texto(assento.get("nome"))
            or _texto(registrado.get("nome")))
    especie = _texto(assento.get("especie")).upper()
    try:
        titulo = CAB.titulo_do_ato(especie) if especie else ""
    except CAB.CabecalhoError:
        titulo = ""

    obs = _texto(assento.get("observacoes")) or _texto(assento.get("teor_livre"))
    if not obs:
        # dados_json às vezes traz nota livre; não inventar prosa.
        dados = assento.get("dados") or {}
        if isinstance(dados, dict):
            obs = _texto(dados.get("observacoes")) or _texto(dados.get("teor"))

    frase_obs = f" {obs}" if obs else ""

    # A QUALIFICAÇÃO DO TITULAR — sem o nome, que já vai em negrito antes.
    qualif = ""
    if especie != "UNIAO_ESTAVEL" and registrado:
        resto = qualificacao_inteira({**registrado, "nome": ""})
        qualif = f", {resto}" if resto else ""

    return {
        "data_do_ato": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "estado_do_ato": _texto(sv.get("estado")) or "Maranhão",
        "uf_do_ato": _texto(sv.get("ri_uf")) or "MA",
        "titulo_do_ato": titulo,
        "nome": nome_em_negrito(nome),
        "qualificacao_do_titular": qualif,
        "frase_da_especie": frase_do_livro_e(especie, assento, por_papel),
        "frase_observacoes": frase_obs,
        "escrevente": escrevente,
        "funcao_do_escrevente": funcao_do_escrevente,
    }


def montar_livro_e_do_assento(assento: dict, pessoas: list[dict],
                              texto: str | None = None, **kw) -> dict:
    """O termo do Livro E montado do assento. Só lê."""
    valores = valores_livro_e_do_assento(assento, pessoas, **kw)
    return montar_do_formulario("LIVRO_E", valores, texto)

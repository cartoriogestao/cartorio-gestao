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

AS FRASES SAÍRAM DO CÓDIGO NO LF06C (19/10/2026), E A REGRA FICOU
    Cada frase ocasional dos quatro termos — a DNV, a hora, os avós, o CPF, o
    cônjuge do falecido, a sentença do Livro E… — mora em
    `modelos_padrao/rcpn/` como PEÇA do termo (`RC_TERMO_OBITO__sepultamento`),
    e a ordem da qualificação das partes é o papel `RC_QUALIFICACAO`. O que
    decide SE a frase entra — o sexo, o plural, o campo vazio, a origem do
    assento — continua aqui. As funções seguem puras: leem o texto por
    `rc_textos`, que dá o padrão da base, ou o ajuste da casa enquanto
    `rc_termo.montar_para_conferir` lavra com `rc_textos.lendo_da_casa`.
"""
from __future__ import annotations

from typing import Any

import rc_textos as TEXTOS


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
# `TERMO_NASCIMENTO` — o texto de fábrica do papel RC_TERMO_NASCIMENTO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/rcpn/RC_TERMO_NASCIMENTO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

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
    # O NATIMORTO SE LAVRA POR ESTE MODELO, E O FATO DELE É TER NASCIDO MORTO
    # — LD01, 21/10/2026. O texto afirmava «nasceu uma criança … que recebeu
    # o nome de» e calava o próprio fato registrado no Livro C-Auxiliar (LRP
    # art. 53, § 1º; art. 54, 5º: «a declaração de que nasceu morta»).
    campo("frase_natimorto", "A declaração de que nasceu morta",
          de_onde="a espécie do assento (natimorto)",
          artigo="LRP art. 53, § 1º, e art. 54, 5º",
          ajuda="«nasceu morta» — só no natimorto; no nascimento não há "
                "menção nem espaço"),
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
    # O REGISTRO TARDIO — 21/10/2026 (hotfix do servidor, LH05). Vem antes
    # das testemunhas do assento, na ordem do texto.
    campo("frase_tardio", "Registro tardio",
          de_onde="a marca de registro tardio, o requerimento e as testemunhas",
          artigo="art. 46 da Lei nº 6.015/1973; art. 249 do Código de Normas",
          ajuda="«Registro lavrado fora do prazo legal … à vista do requerimento "
                "nº … assinado pelas testemunhas …» — **sai vazia** no "
                "registro dentro do prazo; a dispensa das testemunhas é "
                "calculada (menor de 12 anos com DNV), e não impressa"),
    # AS DUAS TESTEMUNHAS DO PARTO SEM ASSISTÊNCIA MÉDICA — LD01, 21/10/2026.
    # O papel TESTEMUNHA existia na espécie e na tela, e o modelo não tinha
    # onde escrevê-las: o parto em residência saía sem os nomes, a profissão,
    # o documento e a residência que a lei manda constar.
    campo("testemunhas", "Testemunhas do assento",
          de_onde="as pessoas de papel TESTEMUNHA (e TESTEMUNHA2, a "
                  "segunda do nascimento)",
          artigo="LRP art. 54, 9º; CN-MA art. 233, IX",
          ajuda="cada uma qualificada (nome, profissão, documento e "
                "residência), e elas também assinam. **Sai inteira** quando "
                "o assento não tem testemunha — e no registro tardio, cujas "
                "testemunhas a frase do tardio já nomeia"),
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
# `TERMO_CASAMENTO` — o texto de fábrica do papel RC_TERMO_CASAMENTO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/rcpn/RC_TERMO_CASAMENTO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

CAMPOS_CASAMENTO: tuple[dict, ...] = (
    campo("data_ato_extenso", "Data do registro, por extenso", exigido=True),
    campo("cidade_do_ato", "Cidade e comarca", exigido=True),
    campo("nubente1_qualificacao", "Primeiro nubente — qualificação",
          exigido=True, artigo="art. 70 da Lei nº 6.015/1973, item 1"),
    campo("nubente2_qualificacao", "Segundo nubente — qualificação",
          exigido=True, artigo="art. 70 da Lei nº 6.015/1973, item 1"),
    campo("frase_habilitacao", "Habilitação",
          de_onde="o processo de habilitação, quando é desta casa",
          artigo="art. 70 da Lei nº 6.015/1973, item 4; CN-MA art. 284, IV",
          ajuda="quando vier de outra serventia, o assento **compra selo "
                "próprio** — item 14.1.6; desta casa ou de fora, a frase diz "
                "a data da publicação dos proclamas"),
    # A DATA DA CELEBRAÇÃO — LD01, 21/10/2026. O termo começava «Em <data do
    # ato>» e ignorava a data do fato, que a certidão imprime como DATA DA
    # CELEBRAÇÃO: celebrado num dia e lavrado no outro, termo e certidão
    # discordavam.
    campo("frase_da_celebracao", "Data da celebração",
          de_onde="`data_fato` do assento",
          artigo="art. 70 da Lei nº 6.015/1973, item 4; CN-MA art. 284, IV",
          ajuda="«em dezenove (19) de outubro de …» — **sai inteira** quando "
                "a data do fato não foi informada"),
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
    campo("filiacao1", "Filiação do primeiro nubente", exigido=True,
          artigo="art. 70 da Lei nº 6.015/1973, item 2; CN-MA art. 284, II",
          ajuda="os nomes dos pais e, entre parênteses, a nacionalidade, a "
                "data de nascimento e a residência de cada um"),
    campo("filiacao2", "Filiação do segundo nubente", exigido=True,
          ajuda="são **quatro** filiações no casamento, e o sistema lia duas"),
    campo("frase_conversao", "Conversão de união estável",
          ajuda="tem caminho e schema próprios no selador, e o número do "
                "processo da união estável é obrigatório"),
    campo("testemunhas", "Testemunhas", exigido=True,
          artigo="art. 70 da Lei nº 6.015/1973, item 6; CC art. 1.534; "
                 "CN-MA art. 284, VI",
          ajuda="cada uma qualificada — nacionalidade, profissão, documento "
                "e residência —, e não só o nome"),
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
# `TERMO_OBITO` — o texto de fábrica do papel RC_TERMO_OBITO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/rcpn/RC_TERMO_OBITO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

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
# `TERMO_LIVRO_E` — o texto de fábrica do papel RC_TERMO_LIVRO_E — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/rcpn/RC_TERMO_LIVRO_E.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

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
     "livro": "A", "no_catalogo": "RC_TERMO_NASCIMENTO", "campos": CAMPOS_NASCIMENTO,
     "conferido_no_papel": True,
     "fonte": "construído dos requisitos do art. 233 do Código de Normas "
              "do TJMA; o termo nº 8.369 desta casa serviu de **conferência**, "
              "e não de fonte",
     "artigo": "art. 233 do Código de Normas do TJMA; art. 54 da Lei nº "
               "6.015/1973"},
    {"chave": "CASAMENTO", "nome": "Termo de casamento",
     "livro": "B", "no_catalogo": "RC_TERMO_CASAMENTO", "campos": CAMPOS_CASAMENTO,
     "conferido_no_papel": False,
     "fonte": "construído dos requisitos do art. 70 da Lei nº 6.015/1973 — "
              "**é assim que o oficial mandou**, em 30/08/2026: os modelos do "
              "E-Ofício não se usam, nem o papel",
     "artigo": "art. 70 da Lei nº 6.015/1973"},
    {"chave": "OBITO", "nome": "Termo de óbito",
     "livro": "C", "no_catalogo": "RC_TERMO_OBITO", "campos": CAMPOS_OBITO,
     "conferido_no_papel": False,
     "fonte": "construído dos doze incisos do art. 255 do Código de Normas "
              "do TJMA, que repete o art. 80 da Lei nº 6.015/1973 — **é assim "
              "que o oficial mandou**, em 30/08/2026",
     "artigo": "art. 80 da Lei nº 6.015/1973"},
    {"chave": "LIVRO_E", "nome": "Termo do Livro E",
     "livro": "E", "no_catalogo": "RC_TERMO_LIVRO_E", "campos": CAMPOS_LIVRO_E,
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
    """O modelo daquele ato, com o `texto` de fábrica LIDO DA BASE.

    **O TEXTO SAIU DESTE MÓDULO NO LF06A** (19/10/2026): mora em
    `modelos_padrao/rcpn/RC_TERMO_<ATO>.txt`, com os mesmos bytes, e chega pela
    base dos padrões. O resto da ficha — campos, livro, de onde veio — continua
    aqui, porque é regra do termo, e não texto.
    """
    for m in MODELOS:
        if m["chave"] == chave:
            import modelos_da_casa as CASA
            return {**m, "texto": CASA.padrao_de(m["no_catalogo"])}
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


def _frase(chave: str, **claros: Any) -> str:
    """A peça de um termo com os claros preenchidos. Só lê.

    **SEM CONEXÃO, E NÃO POR DESCUIDO.** Estas funções são puras e a prévia do
    motor (`modelos_motor_termo`) as chama sem banco: aí sai o padrão da base.
    Na lavratura, `rc_termo.montar_para_conferir` abre
    `rc_textos.lendo_da_casa(con)` em volta da montagem, e a mesma chamada lê
    o ajuste da casa — sem pendurar a conexão em dez assinaturas.
    """
    return TEXTOS.peca(chave, **claros)


def _do_papel(chave: str) -> str:
    """O texto inteiro de um papel do catálogo, sem preencher. Só lê."""
    return TEXTOS.texto(chave)


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


# A ORDEM DA QUALIFICAÇÃO É UM PAPEL DO CATÁLOGO (LF06C). O nome antigo
# `QUALIFICACAO` responde pelo `__getattr__` do fim do módulo.
CHAVE_DA_QUALIFICACAO = "RC_QUALIFICACAO"

# O lugar da parte que não se sabe, enquanto o corpo se preenche. O NUL não
# aparece em texto do livro (o PostgreSQL nem o aceita numa coluna de texto),
# e por isso não se confunde com nada que a pessoa tenha.
_PARTE_VAZIA = "\x00"


def qualificacao_inteira(p: dict, *, feminino: bool | None = None, nome_negrito: bool = False) -> str:
    """A pessoa como o termo desta casa a escreve.

    Medido no termo nº 19.555: **nome, nacionalidade, profissão, RG, CPF,
    naturalidade, data de nascimento e residência** — nessa ordem, e com as
    palavras concordando em gênero («portador»/«portadora», «inscrito»/
    «inscrita», «residente e domiciliado»/«domiciliada»).

    **O QUE NÃO SE SABE NÃO APARECE, E NÃO DEIXA VÍRGULA SOLTA.** «Fulano, ,
    portador do RG n.º ,» é pior que «Fulano»: parece erro de impressão num
    livro que não aceita rasura.

    **A ORDEM É PAPEL, AS FRASES SÃO PEÇAS, E A CONCORDÂNCIA É CÓDIGO** — LF06C,
    19/10/2026. A ordem das partes é o corpo do papel `RC_QUALIFICACAO`
    (`{nome}, {nacionalidade}, … {residencia}`), que a casa pode reordenar na
    tela de Modelos; a frase de cada parte («portadora do RG n.º …») é peça
    dele, uma para cada gênero. O que NÃO vai para o texto editável são as
    duas regras: qual das peças concorda com o sexo da pessoa, e que a parte
    sem dado some — com a vírgula que a separa (`_juntar_partes`). Escritas
    no texto, a casa teria de reescrevê-las em cada ajuste, e um ajuste que
    as esquecesse deixaria a vírgula solta no livro.
    """
    if not p:
        return ""
    f = (feminino if feminino is not None
         else _texto(p.get("sexo")).upper().startswith("F"))
    nome = _texto(p.get("nome")).strip()
    if nome_negrito and nome:
        nome = nome_em_negrito(nome)
    partes = {"nome": nome,
              "nacionalidade": _texto(p.get("nacionalidade")),
              "profissao": _texto(p.get("profissao")),
              "rg": "", "cpf": "", "naturalidade": "", "nascimento": "",
              "residencia": ""}
    rg = _texto(p.get("documento_numero")) if \
        _texto(p.get("documento_tipo")).upper() in ("RG", "") else ""
    if rg:
        partes["rg"] = _frase("RC_QUALIFICACAO__rg_feminino" if f
                              else "RC_QUALIFICACAO__rg_masculino", numero=rg)
    cpf = _texto(p.get("cpf")) or (
        _texto(p.get("documento_numero"))
        if _texto(p.get("documento_tipo")).upper() == "CPF" else "")
    if cpf:
        partes["cpf"] = _frase("RC_QUALIFICACAO__cpf_feminino" if f
                               else "RC_QUALIFICACAO__cpf_masculino", numero=cpf)
    nat = _texto(p.get("naturalidade_cidade"))
    if nat:
        uf = _texto(p.get("naturalidade_uf"))
        partes["naturalidade"] = _frase("RC_QUALIFICACAO__naturalidade",
                                        lugar=nat + (f"/{uf}" if uf else ""))
    nasc = _texto(p.get("data_nascimento"))[:10]
    if nasc and len(nasc) == 10:
        d, m, a = nasc[8:10], nasc[5:7], nasc[:4]
        partes["nascimento"] = _frase(
            "RC_QUALIFICACAO__nascimento_feminino" if f
            else "RC_QUALIFICACAO__nascimento_masculino", data=f"{d}/{m}/{a}")
    end = _texto(p.get("endereco"))
    if end:
        pedaco = [end]
        for chave in ("bairro", "cidade"):
            v = _texto(p.get(chave))
            if v:
                pedaco.append(v)
        uf = _texto(p.get("uf"))
        residencia = ", ".join(pedaco) + (f"/{uf}" if uf else "")
        partes["residencia"] = _frase(
            "RC_QUALIFICACAO__residencia_feminino" if f
            else "RC_QUALIFICACAO__residencia_masculino", endereco=residencia)
    return _juntar_partes(_do_papel(CHAVE_DA_QUALIFICACAO), partes)


def _juntar_partes(corpo: str, partes: dict[str, str]) -> str:
    """O corpo da qualificação com as partes; a que falta some. Só calcula.

    A parte vazia entra como marca e sai **com o separador que a precede**
    («, » ou «; ») — a mesma conta do `", ".join` de antes do LF06C, agora
    sobre a ordem que o papel diz. No começo do texto não há separador antes:
    ali as marcas saem com o que vem DEPOIS delas, senão a qualificação de quem
    não tem nome começaria por vírgula.
    """
    import re
    montado = corpo.format(**{k: v or _PARTE_VAZIA for k, v in partes.items()})
    montado = re.sub(r"^(?:\s*\x00\s*[,;]?)+\s*", "", montado)
    return re.sub(r"\s*[,;]?\s*\x00", "", montado)


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
    # A expressão pega o trecho de brancos inteiro e a função decide
    # (CodeQL py/polynomial-redos, 28/10/2026): `\s*\n\s*` e `\s+([,.;:])`
    # varriam de novo um trecho longo a partir de cada espaço, em tempo
    # quadrático. O resultado é o mesmo: o trecho com quebra vira um espaço,
    # e o que vem antes da pontuação sai.
    texto = re.sub(r"\s+", lambda m: " " if "\n" in m.group() else m.group(), texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\s+([,.;:]?)", lambda m: m.group(1) or m.group(), texto)
    return texto.strip()


def frase_dos_gemeos(assento: dict, registrado: dict | None) -> str:
    """«, gêmeo, o 1º na ordem de nascimento», ou nada. Só calcula.

    **O PARTO MÚLTIPLO QUE O BALCÃO INFORMA VAI AO TERMO** — LD01, 21/10/2026.
    `{frase_gemeos}` só saía de quem a passasse à mão, e a lavratura não
    passava: o termo calava o que a certidão já dizia («GÊMEO: SIM»). A lei
    manda constar o fato de ser gêmeo (LRP art. 54, 3º) e, no assento de cada
    um, a ordem de nascimento (art. 63; CN-MA art. 234).

    O FATO VEM DO `ibge_gemeo` (2 gêmeo, 3 trigêmeo ou mais — a régua é a de
    `rc_gemeos.e_parto_multiplo`), e a ORDEM do `gemeo_ordem`, que é outra
    pergunta: sem ela a frase diz só que é gêmeo, e `rc_gemeos.pendentes`
    continua cobrando a ordem. A palavra concorda com o sexo do registrado;
    o texto de cada forma é peça do termo.
    """
    import rc_gemeos as GEMEOS
    if not GEMEOS.e_parto_multiplo((assento or {}).get("ibge_gemeo")):
        return ""
    feminino = _feminino(registrado)
    try:
        ordem = int((assento or {}).get("gemeo_ordem") or 0)
    except (TypeError, ValueError):
        ordem = 0
    if ordem >= 1:
        return ", " + _frase("RC_TERMO_NASCIMENTO__gemea_na_ordem" if feminino
                             else "RC_TERMO_NASCIMENTO__gemeo_na_ordem",
                             ordem=ordem)
    return ", " + _frase("RC_TERMO_NASCIMENTO__gemea" if feminino
                         else "RC_TERMO_NASCIMENTO__gemeo")


def _lista_de_qualificados(qualificacoes: list[str]) -> str:
    """«A, qualificada; e B, qualificado» — a lista de pessoas qualificadas.

    A qualificação de cada uma tem vírgulas por dentro; separá-las com a
    vírgula da lista misturaria as pessoas. O ponto e vírgula separa uma da
    outra, e o «e» fica antes da última. Só calcula."""
    limpos = [q for q in (_texto(x) for x in qualificacoes) if q]
    # SÓ COM NOMES, A LISTA É A DE SEMPRE — «A, B e C». O ponto e vírgula só
    # entra quando há qualificação para separar.
    if not any("," in q for q in limpos):
        return _lista_por_extenso(limpos)
    if len(limpos) <= 1:
        return "".join(limpos)
    return "; ".join(limpos[:-1]) + "; e " + limpos[-1]


def _testemunhas_qualificadas(pessoas: list[dict] | None) -> str:
    """As pessoas de papel TESTEMUNHA, cada uma com a qualificação inteira,
    na ordem em que entraram. Só calcula.

    No NASCIMENTO a segunda gaveta grava `TESTEMUNHA2` (o papel do registro
    tardio, 21/10/2026 — LH05), e ela é testemunha do assento do mesmo jeito."""
    return _lista_de_qualificados([
        qualificacao_inteira(p) for p in pessoas or []
        if _texto(p.get("papel")).upper() in ("TESTEMUNHA", "TESTEMUNHA2")
        and _texto(p.get("nome"))])


def _filiacao_qualificada(mae: dict | None, pai: dict | None,
                          campos: tuple[str, ...]) -> str:
    """«ANA e JOÃO (respectivamente: brasileira, …; e brasileiro, …)». Só calcula.

    **OS NOMES FICAM JUNTOS, E A QUALIFICAÇÃO VAI DEPOIS** — LD01, 21/10/2026.
    O termo dava só os nomes dos pais, e a lei pede mais: no casamento a
    nacionalidade, a data de nascimento e a residência (LRP art. 70, 2º; CN-MA
    art. 284, II); no óbito a profissão, a naturalidade e a residência (LRP
    art. 80, 5º; CN-MA art. 255, VI). `campos` diz quais partes da
    qualificação entram — o resto do cadastro da pessoa não vai a este termo.

    Os dois nomes continuam lado a lado, como o termo sempre os escreveu; a
    qualificação de cada um vem entre parênteses, na ordem dos nomes
    («respectivamente»). Só um com qualificação, ela leva o nome junto, para
    não ficar dito de quem não é. Sem qualificação nenhuma, só os nomes.
    """
    pais = [p for p in (mae, pai) if p and _texto(p.get("nome"))]
    nomes = _dois_nomes(mae or {}, pai or {})
    if not pais:
        return nomes
    quais = [qualificacao_inteira({**{c: p.get(c) for c in campos},
                                   "sexo": p.get("sexo"), "nome": ""})
             for p in pais]
    if not any(quais):
        return nomes
    if all(quais):
        dentro = (quais[0] if len(quais) == 1
                  else _frase("RC_QUALIFICACAO__respectivamente",
                              qualificacoes=_lista_de_qualificados(quais)))
    else:
        dentro = "; ".join(f"{_texto(p.get('nome'))}, {q}"
                           for p, q in zip(pais, quais) if q)
    return f"{nomes} ({dentro})"


#: As partes da qualificação dos pais que cada termo pede.
CAMPOS_DOS_PAIS_NO_CASAMENTO = ("nacionalidade", "data_nascimento", "endereco",
                                "bairro", "cidade", "uf")
CAMPOS_DOS_PAIS_NO_OBITO = ("profissao", "naturalidade_cidade",
                            "naturalidade_uf", "endereco", "bairro", "cidade",
                            "uf")


def _testemunhas_do_tardio(pessoas: list[dict] | None) -> list[dict]:
    """As duas testemunhas do requerimento do tardio (art. 249, II), a
    primeira antes da segunda, só as que têm nome. Só calcula."""
    return [p for papel in ("TESTEMUNHA", "TESTEMUNHA2")
            for p in (pessoas or [])
            if _texto(p.get("papel")).upper() == papel
            and _texto(p.get("nome"))]


def frase_do_tardio(assento: dict, pessoas: list[dict]) -> str:
    """O registro tardio no termo — art. 46 da Lei 6.015/1973 e art. 249 do
    Código de Normas. Só calcula. 21/10/2026.

    **A DISPENSA DAS TESTEMUNHAS SE CALCULA, E NÃO SE IMPRIME** — o modelo do
    E-Ofício a afirmava em toda folha, e o art. 249, II a condiciona (menor de
    12 anos *e* DNV). A régua é `rc_assento.regra_das_testemunhas_do_tardio`,
    a mesma que a lavratura usa para recusar.

    O TEXTO DE CADA PEDAÇO É PEÇA DE `RC_TERMO_NASCIMENTO` (LF06C): no
    servidor ele estava escrito aqui, e o texto do papel mora na base. Os
    bytes são os do servidor; a vírgula que junta os pedaços, o espaço da
    frente e o ponto final são do código.
    """
    import rc_assento as RC
    if not RC.e_tardio(assento.get("registro_tardio")):
        return ""
    req = _texto(assento.get("tardio_requerimento"))
    frase = " " + (_frase("RC_TERMO_NASCIMENTO__tardio_com_requerimento",
                          requerimento=req) if req
                   else _frase("RC_TERMO_NASCIMENTO__tardio"))
    testemunhas = _testemunhas_do_tardio(pessoas)
    if testemunhas:
        frase += ", " + _frase(
            "RC_TERMO_NASCIMENTO__tardio_testemunhas",
            testemunhas=" e ".join(qualificacao_inteira(p) for p in testemunhas))
    regra = RC.regra_das_testemunhas_do_tardio(assento, pessoas)
    if regra["dispensada"] and not testemunhas:
        frase += ", " + _frase("RC_TERMO_NASCIMENTO__tardio_dispensa")
    return frase + "."


def valores_do_assento(assento: dict, pessoas: list[dict], *,
                       sv: dict | None = None,
                       frase_gemeos: str = "",
                       escrevente: str = "",
                       funcao_do_escrevente: str = "") -> dict:
    """Os claros do termo de nascimento, preenchidos do que o assento tem.

    **AS FRASES OCASIONAIS SAEM INTEIRAS, COM A PONTUAÇÃO.** Cada uma já vem
    com a vírgula que a precede, para que a ausência não deixe rastro — foi o
    que o oficial determinou sobre os gêmeos, e vale para todas.

    `frase_gemeos` passada por quem chama vence a que o assento dá (é o
    caminho de antes do LD01, que a prévia do motor ainda usa); vazia, a
    frase sai do parto múltiplo informado (`frase_dos_gemeos`).
    """
    por_papel: dict[str, dict] = {}
    for p in pessoas or []:
        por_papel.setdefault(_texto(p.get("papel")).upper(), p)

    registrado = por_papel.get("REGISTRADO", {})
    mae = por_papel.get("MAE", {})
    pai = por_papel.get("PAI", {})
    sv = sv or {}

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
    # O TEXTO DE CADA FRASE É PEÇA DE `RC_TERMO_NASCIMENTO` (LF06C); a vírgula
    # que a precede já mora na peça, e a decisão de ela entrar continua aqui.
    if avos1 and avos2:
        frase_avos = _frase("RC_TERMO_NASCIMENTO__avos", avos1=avos1,
                            avos2=avos2)
    elif avos1 or avos2:
        frase_avos = _frase("RC_TERMO_NASCIMENTO__avos_de_um_lado",
                            filiacao="1" if avos1 else "2",
                            avos=avos1 or avos2)
    else:
        frase_avos = ""
    qualificacao_do_pai = qualificacao_inteira(pai)
    natimorto = _texto(assento.get("especie")).upper() == "NATIMORTO"
    # O NATIMORTO NÃO TEM DNV: o documento que o balcão apresenta é a
    # Declaração de Óbito (LRP art. 53; CNN art. 479-A), e o termo diz qual.
    numero_do = _texto(assento.get("numero_do")) if natimorto else ""
    testemunhas = _testemunhas_qualificadas(pessoas)
    frase_tardio = frase_do_tardio(assento, pessoas)
    tardio_com_testemunhas = bool(frase_tardio
                                  and _testemunhas_do_tardio(pessoas))

    return {
        "data_do_ato": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "estado_do_ato": _texto(sv.get("estado")) or "Maranhão",
        "uf_do_ato": _texto(sv.get("ri_uf")) or "MA",
        "declarante_qualificacao": qualificacao_inteira(
            por_papel.get("DECLARANTE", {})),
        "frase_dnv": (_frase("RC_TERMO_NASCIMENTO__dnv", dnv=dnv) if dnv
                      else _frase("RC_TERMO_NASCIMENTO__declaracao_de_obito",
                                  numero=numero_do) if numero_do else ""),
        "data_do_fato": data_do_termo(assento.get("data_fato"),
                                      com_numeros=True),
        "frase_hora": _frase_da_hora(assento.get("hora_fato"),
                                     "RC_TERMO_NASCIMENTO__hora",
                                     "RC_TERMO_NASCIMENTO__hora_cheia"),
        "local_do_fato": local,
        # «nasceu morta uma criança» — o fato do Livro C-Auxiliar (LD01).
        "frase_natimorto": (" " + _frase("RC_TERMO_NASCIMENTO__natimorto")
                            if natimorto else ""),
        "sexo": {"M": "Masculino", "F": "Feminino"}.get(
            _texto(registrado.get("sexo")).upper()[:1], ""),
        "frase_cor": _frase("RC_TERMO_NASCIMENTO__cor", cor=cor) if cor else "",
        "nome": nome_em_negrito(assento.get("nome")),
        "frase_gemeos": frase_gemeos or frase_dos_gemeos(assento, registrado),
        # **O GENERO VEM DO SEXO DA PESSOA, E NAO DA POSICAO.** Forcei
        # feminino na filiacao 1 e o termo saiu «EVANDRO SOUSA SALES,
        # BRASILEIRO, LAVRADOR, INSCRITA no CPF, NASCIDA no dia...» —
        # medido num assento real em 30/08/2026. Ha assentos de casais do
        # mesmo sexo, e ha dado trocado no acervo: a posicao nao diz o
        # genero de ninguem.
        "filiacao1_qualificacao": qualificacao_inteira(mae),
        "frase_filiacao2": (_frase("RC_TERMO_NASCIMENTO__filiacao2",
                                   filiacao2=qualificacao_do_pai)
                            + frase_do_casamento_dos_pais(assento)
                            if qualificacao_do_pai else ""),
        "frase_idade_da_genitora": (
            _frase("RC_TERMO_NASCIMENTO__idade_da_mae", idade=idade)
            if idade else ""),
        "frase_avos": frase_avos,
        # O PONTO QUE FECHA A FILIAÇÃO É DO CÓDIGO: ele sai mesmo sem a frase.
        "frase_naturalidade": (
            ". " + _frase("RC_TERMO_NASCIMENTO__naturalidade", naturalidade=nat)
            if nat else "."),
        # CPF E «PRIMEIRO REGISTRO» DENTRO DO TEOR - pedido do oficial em
        # 09/10/2026: o CPF entra no termo, sem averbacao. Concorda com o sexo
        # do registrado; sem CPF a frase some inteira (sem traco solto).
        "frase_primeiro_registro": (
            "" if (_texto(assento.get("origem")).upper() in ORIGENS_SEM_PRIMEIRO_REGISTRO
                   or _texto(assento.get("especie")).upper() == "NATIMORTO")
            else " " + _frase("RC_TERMO_NASCIMENTO__primeiro_registro")),
        "frase_cpf": (f" {frase_do_cpf(cpf, registrado.get('sexo'))}"
                      if cpf else ""),
        # O REGISTRO TARDIO (art. 46 da LRP; art. 249 do CN-MA) — vazia no
        # registro dentro do prazo.
        "frase_tardio": frase_tardio,
        # AS TESTEMUNHAS DO ASSENTO (LRP art. 54, 9º), antes do fecho — que é
        # onde elas assinam com o declarante.
        # A MESMA PESSOA NÃO SE ESCREVE DUAS VEZES (LH05): no tardio quem
        # nomeia e qualifica as testemunhas é a frase do tardio.
        "testemunhas": (" " + _frase("RC_TERMO_NASCIMENTO__testemunhas",
                                     testemunhas=testemunhas)
                        if testemunhas and not tardio_com_testemunhas
                        else ""),
        # O ESPACO DEPOIS DO PONTO E PARTE DA FRASE. Sem ele sai
        # «...18.Cidade Exemplo/MA» — medido em 30/08/2026.
        "frase_matricula": (_frase("RC_TERMO_NASCIMENTO__matricula",
                                   matricula=matricula) if matricula else ""),
        "escrevente": escrevente,
        "funcao_do_escrevente": funcao_do_escrevente,
    }


def _frase_da_hora(hora_fato: Any, peca_com_minuto: str, peca_cheia: str) -> str:
    """«, às 14:30», «, às 14 horas», ou nada. Só calcula.

    A MESMA REGRA NOS DOIS TERMOS (nascimento e óbito), cada um com as suas
    peças: com hora e minuto, a primeira; só com a hora, a segunda; sem a hora
    — ainda que haja minuto —, a frase não entra.
    """
    h, _, m = _texto(hora_fato).partition(":")
    if h.strip() and m.strip():
        return _frase(peca_com_minuto, hora=h.strip(), minuto=m.strip())
    if h.strip():
        return _frase(peca_cheia, hora=h.strip())
    return ""


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
#
# As duas frases sao pecas de RC_TERMO_NASCIMENTO desde o LF06C
# (`__primeiro_registro`, `__cpf_feminino`, `__cpf_masculino`); o nome antigo
# `FRASE_PRIMEIRO_REGISTRO` responde pelo `__getattr__` do fim do modulo. A
# origem, a ancora e a palavra que acusa o «primeiro registro» ja escrito
# ficam aqui: sao regra, e o texto do livro e lido por elas.
ORIGENS_SEM_PRIMEIRO_REGISTRO = ("EOFICIO", "ACERVO")
ANCORA_DO_FECHO = "Lido e achado conforme"
JA_TEM_PRIMEIRO_REGISTRO = "primeiro registro"


def _cpf_formatado(cpf: Any) -> str:
    """O CPF como o termo o escreve. So calcula.

    Com onze digitos, `000.000.000-00`; com outra conta, como veio — o termo
    nao corrige o que o balcao digitou, e o passo do CPF avisa depois.
    """
    bruto = _texto(cpf)
    n = "".join(ch for ch in bruto if ch.isdigit())
    if len(n) == 11:
        return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"
    return bruto


def frase_do_cpf(cpf: Any, sexo: Any = "", *, con: Any = None) -> str:
    """«Inscrito(a) no CPF n.º 000.000.000-00.» - vazio sem CPF. So le.

    `con` e de quem lavra o teor digitado (`completar_teor_nascimento`): com
    ela a frase sai do ajuste da casa; sem ela, do padrao (ou de
    `rc_textos.lendo_da_casa`, na montagem do termo).
    """
    formatado = _cpf_formatado(cpf)
    if not formatado:
        return ""
    chave = ("RC_TERMO_NASCIMENTO__cpf_feminino"
             if _texto(sexo).upper()[:1] == "F"
             else "RC_TERMO_NASCIMENTO__cpf_masculino")
    return TEXTOS.peca(chave, con, cpf=formatado)


def completar_teor_nascimento(teor: Any, *, cpf: Any = "", sexo: Any = "",
                              con: Any = None) -> str:
    """Poe «primeiro registro» e o CPF no teor digitado, se faltarem. So le.

    O teor do balcao chega pronto (textarea / rascunho) e o CPF da conferencia
    so era gravado DEPOIS de lavrar - por isso o termo saia sem ele e o CPF ia
    por averbacao. Entra antes de «Lido e achado conforme»; sem essa ancora
    (texto proprio) nao adivinha o lugar e devolve o texto como veio.
    Idempotente: o que ja esta no texto nao entra de novo.

    **O CPF JA ESCRITO SE PROCURA PELO NUMERO, E NAO PELA FRASE** (LF06C): a
    frase e peca que a casa pode reescrever, e recortar o numero de dentro
    dela («n.º ») quebraria no primeiro ajuste. `con` vem da lavratura, para
    as duas frases sairem do ajuste da casa.
    """
    texto = _texto(teor)
    if not texto:
        return "" if teor is None else str(teor)
    i = texto.find(ANCORA_DO_FECHO)
    if i < 0:
        return texto
    faltam = []
    if JA_TEM_PRIMEIRO_REGISTRO not in texto.lower():
        faltam.append(TEXTOS.peca("RC_TERMO_NASCIMENTO__primeiro_registro", con))
    formatado = _cpf_formatado(cpf)
    if formatado:
        n = "".join(ch for ch in _texto(cpf) if ch.isdigit())
        # O `rstrip` e o da forma de antes, que recortava o numero da frase e
        # lhe tirava o ponto final junto com qualquer ponto do fim do numero.
        if formatado.rstrip(".") not in texto and (not n or n not in texto):
            faltam.append(frase_do_cpf(cpf, sexo, con=con))
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
        return _frase("RC_TERMO_CASAMENTO__nomes_mantidos")
    if len(mudou) == 1:
        antes, depois = mudou[0]
        return _frase("RC_TERMO_CASAMENTO__nome_de_um", antes=antes,
                      depois=depois)
    return _frase("RC_TERMO_CASAMENTO__nomes_dos_dois",
                  nomes=_lista_por_extenso([d for _, d in mudou]))


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
        partes.append(_frase("RC_TERMO_CASAMENTO__documentos_apresentados",
                             lista=_lista_por_extenso(apresentados)))
    if dispensados:
        partes.append(_frase("RC_TERMO_CASAMENTO__documentos_dispensados",
                             lista=_lista_por_extenso(dispensados)))
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
    for p in pessoas or []:
        papel = _texto(p.get("papel")).upper()
        if papel != "TESTEMUNHA":
            por_papel.setdefault(papel, p)
    sv = sv or {}

    n1 = por_papel.get("NUBENTE1", {})
    n2 = por_papel.get("NUBENTE2", {})

    de_fora = _texto(assento.get("habilitacao_serventia"))
    proclamas = _data_br(assento.get("proclamas_data"))
    # Sem habilitação de fora, o ponto fecha a relação dos documentos — e, com
    # a data do edital desta casa, a frase dos proclamas vem logo depois
    # (LRP art. 70, 4º; CN-MA art. 284, IV — LD01, 21/10/2026: a data só se
    # escrevia quando a habilitação era de fora).
    if not de_fora:
        frase_habilitacao = (". " + _frase(
            "RC_TERMO_CASAMENTO__habilitacao_desta_casa_proclamas",
            data=proclamas) if proclamas else ".")
    elif proclamas:
        frase_habilitacao = " " + _frase(
            "RC_TERMO_CASAMENTO__habilitacao_de_fora_proclamas",
            serventia=de_fora, data=proclamas)
    else:
        frase_habilitacao = " " + _frase(
            "RC_TERMO_CASAMENTO__habilitacao_de_fora", serventia=de_fora)
    # A RELAÇÃO DOS DOCUMENTOS (art. 70, 5º): a da habilitação desta casa vem
    # de `hc_documentos`; a de fora, do que o balcão digitou (13/10/2026).
    docs_digitados = _texto(assento.get("documentos_apresentados"))
    relacao = relacao_de_documentos(documentos) or (
        _frase("RC_TERMO_CASAMENTO__documentos_apresentados",
               lista=docs_digitados) if docs_digitados else "")

    processo = _texto(assento.get("uniao_estavel_processo"))
    frase_conversao = (
        _frase("RC_TERMO_CASAMENTO__conversao", processo=processo)
        if processo else "")

    # A DATA DA CELEBRAÇÃO É A DO FATO, e a certidão a imprime com esse nome;
    # o termo a diz junto de «foram declarados casados» (LD01).
    celebracao = data_do_termo(assento.get("data_fato"))

    return {
        "data_ato_extenso": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "nubente1_qualificacao": qualificacao_inteira(n1, nome_negrito=True)
                                 + frase_do_casamento_anterior(assento, "nubente1"),
        "nubente2_qualificacao": qualificacao_inteira(n2, nome_negrito=True)
                                 + frase_do_casamento_anterior(assento, "nubente2"),
        "documentos_apresentados": relacao,
        "frase_habilitacao": frase_habilitacao,
        "frase_da_celebracao": (" " + _frase("RC_TERMO_CASAMENTO__celebracao",
                                             data=celebracao)
                                if celebracao else ""),
        "regime_bens": (regime_por_extenso(assento.get("regime_bens"))
                        + frase_do_pacto(assento)),
        "frase_dos_nomes": frase_dos_nomes(n1, n2),
        "filiacao1": _filiacao_qualificada(por_papel.get("MAE_NUBENTE1"),
                                           por_papel.get("PAI_NUBENTE1"),
                                           CAMPOS_DOS_PAIS_NO_CASAMENTO),
        "filiacao2": _filiacao_qualificada(por_papel.get("MAE_NUBENTE2"),
                                           por_papel.get("PAI_NUBENTE2"),
                                           CAMPOS_DOS_PAIS_NO_CASAMENTO),
        "frase_conversao": frase_conversao,
        # AS TESTEMUNHAS QUALIFICADAS (LRP art. 70, 6º; CN-MA art. 284, VI —
        # LD01): o termo dava só os nomes.
        "testemunhas": _testemunhas_qualificadas(pessoas),
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


#: As marcas do óbito que NÃO são itens do art. 255 do CN-MA e, por isso,
#: não entram na declaração do § 1º. Ver `frase_dos_ignorados`.
_MARCAS_FORA_DO_ART_255 = frozenset({"obito_desconhecido"})


def frase_dos_ignorados(marcas: dict) -> str:
    """A declaracao do art. 255, § 1o. So calcula.

    **A NORMA MANDA ESCREVER QUE SE PERGUNTOU**, e nao deixar o campo vazio: se
    nao for possivel constar todos os elementos, o oficial «declarara, no corpo
    do registro, que fez a pergunta e que o declarante ignorava» o que falta.

    Por isso `rc_marcas_do_obito` guarda **tres** estados e nao dois: «sim»,
    «nao» e **«nao perguntado»** — e sao os nao perguntados que entram nesta
    frase. Um campo vazio nao distingue «o falecido nao tinha bens» de «ninguem
    perguntou se tinha», e o termo tem de dizer qual dos dois foi.

    **«PESSOA NÃO IDENTIFICADA» NÃO É ITEM DO ART. 255** — LT01, 20/10/2026.
    A marca existe para o assento de desconhecido (LRP art. 81; CN-MA art.
    257), que tem teor próprio. Entrando nesta lista, a pergunta não
    respondida fazia o termo de uma falecida com nome e CPF declarar, assinado,
    que «o declarante ignorava: pessoa não identificada».
    """
    import rc_marcas_do_obito as MO

    ignorados = []
    for m in MO.MARCAS:
        if m["chave"] in _MARCAS_FORA_DO_ART_255:
            continue
        if _texto((marcas or {}).get(m["chave"])) == MO.NAO_PERGUNTADO:
            ignorados.append(_texto(m.get("no_termo")) or
                             _texto(m["rotulo"]).lower())
    if not ignorados:
        return ""
    # Os itens são os rótulos de `rc_marcas_do_obito` — a lista é regra e vem
    # de lá; a frase que os declara é peça do termo (LF06C).
    return _frase("RC_TERMO_OBITO__ignorados",
                  itens=_lista_por_extenso(ignorados))


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
    if not nome:
        return (_frase("RC_TERMO_OBITO__estado_civil", estado_civil=estado_civil)
                if estado_civil else "")
    # TRÊS RAMOS DE REDAÇÃO, CADA UM UMA PEÇA (LF06C): com o estado civil, a
    # frase começa por ele; sem, diz se o cônjuge ficou («Deixou») ou se foi
    # antes («Teve»).
    pre_morto = _texto(assento.get("obito_conjuge_situacao")).upper() == "PRE_MORTO"
    if estado_civil:
        frase = _frase("RC_TERMO_OBITO__conjuge_pre_morto" if pre_morto
                       else "RC_TERMO_OBITO__conjuge_sobrevivente",
                       estado_civil=estado_civil, nome=nome)
    else:
        frase = _frase("RC_TERMO_OBITO__teve_conjuge" if pre_morto
                       else "RC_TERMO_OBITO__deixou_conjuge", nome=nome)
    if cartorio:
        frase += _frase("RC_TERMO_OBITO__casamento_do_conjuge",
                        cartorio=cartorio)
    return frase + "."


def frase_dos_filhos_do_falecido(assento: dict, marca_texto: str) -> str:
    """Art. 80, 7º; CN art. 255, VIII — se deixou filhos, o nome e a idade de
    cada um. A lista é texto livre, um por linha. So calcula."""
    linhas = [ln.strip(" ;,.") for ln in _texto(assento.get("obito_filhos")).splitlines()]
    linhas = [ln for ln in linhas if ln]
    if not linhas:
        return marca_texto
    return _frase("RC_TERMO_OBITO__filhos", filhos="; ".join(linhas))


def frase_dos_herdeiros(assento: dict) -> str:
    """CN art. 255, XI — herdeiros menores ou interditados. So calcula.

    O espaço da frente é da junção com a frase dos bens, e não da peça."""
    v = _texto(assento.get("obito_herdeiros_menores")).upper()
    if v == "SIM":
        return " " + _frase("RC_TERMO_OBITO__herdeiros_sim")
    if v == "NAO":
        return " " + _frase("RC_TERMO_OBITO__herdeiros_nao")
    return ""


def frase_do_casamento_anterior(assento: dict, qual: str) -> str:
    """Art. 70, 3º; CN art. 284, III — o cônjuge precedente e a data da
    dissolução, junto da qualificação do nubente. So calcula."""
    nome = _texto(assento.get(f"{qual}_conjuge_anterior"))
    if not nome:
        return ""
    data = _data_br(assento.get(f"{qual}_dissolucao_data"))
    if data:
        return _frase("RC_TERMO_CASAMENTO__casamento_anterior_dissolvido",
                      nome=nome, data=data)
    return _frase("RC_TERMO_CASAMENTO__casamento_anterior", nome=nome)


def frase_do_pacto(assento: dict) -> str:
    """Art. 70, 7º; CN art. 284, VII — data e serventia da escritura de
    pacto antenupcial. So calcula."""
    data = _data_br(assento.get("pacto_data"))
    serventia = _texto(assento.get("pacto_serventia"))
    if data and serventia:
        return _frase("RC_TERMO_CASAMENTO__pacto_data_serventia", data=data,
                      serventia=serventia)
    if data:
        return _frase("RC_TERMO_CASAMENTO__pacto_data", data=data)
    if serventia:
        return _frase("RC_TERMO_CASAMENTO__pacto_serventia",
                      serventia=serventia)
    return ""


def frase_do_casamento_dos_pais(assento: dict) -> str:
    """Art. 54, 7º — «lugar e cartório onde se casaram» os pais. So calcula."""
    lugar = _texto(assento.get("pais_casamento_lugar"))
    cartorio = _texto(assento.get("pais_casamento_cartorio"))
    if lugar and cartorio:
        return _frase("RC_TERMO_NASCIMENTO__pais_casados_lugar_cartorio",
                      lugar=lugar, cartorio=cartorio)
    if lugar:
        return _frase("RC_TERMO_NASCIMENTO__pais_casados_lugar", lugar=lugar)
    if cartorio:
        return _frase("RC_TERMO_NASCIMENTO__pais_casados_cartorio",
                      cartorio=cartorio)
    return ""


def _idade_por_extenso(nascimento: Any, quando: Any) -> str:
    """«76 anos», «1 ano», «menos de um ano», ou nada. Só calcula.

    A CONTA É A DA CASA (`rc_assento.idade_na_data`, que desconta o
    aniversário que não chegou), e não outra: o termo e a certidão do óbito
    têm de dizer a mesma idade."""
    import rc_assento as RC
    anos = RC.idade_na_data(nascimento, quando)
    if anos is None:
        return ""
    if anos == 0:
        return "menos de um ano"
    return f"{anos} ano" + ("s" if anos != 1 else "")


def frase_do_sexo_idade_e_cor(falecido: dict, assento: dict) -> str:
    """«, do sexo feminino, com 76 anos de idade, de cor parda». Só calcula.

    **O TERMO DIZIA SÓ A DATA DE NASCIMENTO** — LD01, 21/10/2026 — e a
    certidão imprime a idade e a cor («IDADE 76 anos», «COR OU RAÇA PARDA»)
    que o termo não declarava. A lei pede os três (LRP art. 80, 3º; CN-MA
    art. 255, III: «o nome, sexo, idade, a data do nascimento, cor…»). Cada
    parte é peça do termo, e a que não se sabe some com a vírgula dela. A
    cor é a da lista fechada da casa (`rc_assento.CORES_E_RACAS`), em
    minúsculas porque vai no meio da frase.
    """
    import rc_assento as RC
    partes = []
    sexo = {"M": "masculino", "F": "feminino"}.get(
        _texto((falecido or {}).get("sexo")).upper()[:1], "")
    if sexo:
        partes.append(_frase("RC_TERMO_OBITO__sexo", sexo=sexo))
    idade = _idade_por_extenso((falecido or {}).get("data_nascimento"),
                               (assento or {}).get("data_fato"))
    if idade:
        partes.append(_frase("RC_TERMO_OBITO__idade", idade=idade))
    bruta = _texto((assento or {}).get("cor_raca"))
    cor = RC.CORES_E_RACAS.get(bruta.upper(), bruta).lower()
    if cor:
        partes.append(_frase("RC_TERMO_OBITO__cor", cor=cor))
    return "".join(partes)


#: A natureza da morte, no código do IBGE que o balcão escolhe
#: (`ibge_remessa.NATUREZA_DO_OBITO`), como o termo a escreve. O 9
#: («ignorado») não vira palavra: o termo não afirma natureza que ninguém
#: declarou.
NATUREZA_DA_MORTE_NO_TERMO: dict[int, str] = {1: "natural", 2: "violenta"}


def frase_da_causa(assento: dict) -> str:
    """«A morte foi natural, tendo como causa …, atestada por …, CRM …». Só
    calcula.

    **SE A MORTE FOI NATURAL OU VIOLENTA É ITEM PRÓPRIO DA LEI** — LD01,
    21/10/2026. A natureza que o balcão informa (`ibge_natureza_obito`) ia só
    para a remessa do IBGE, e a peça escrevia «A morte foi {causa}» (LRP art.
    80, 8º; CN-MA art. 255, IX). Agora a natureza entra quando foi declarada;
    quando o próprio texto da causa já começa por ela («natural, por …»), a
    peça de antes basta, para o termo não dizer a palavra duas vezes. Sem
    natureza declarada, a frase é a de antes.
    """
    a = assento or {}
    causa = _texto(a.get("causa_morte"))
    try:
        natureza = NATUREZA_DA_MORTE_NO_TERMO.get(
            int(a.get("ibge_natureza_obito") or 0), "")
    except (TypeError, ValueError):
        natureza = ""
    atestante = _texto(a.get("atestante"))
    documento_do_atestante = _texto(a.get("atestante_documento"))
    if natureza and causa and not causa.lower().startswith(natureza):
        frase = _frase("RC_TERMO_OBITO__natureza_e_causa", natureza=natureza,
                       causa=causa)
    elif causa:
        frase = _frase("RC_TERMO_OBITO__causa", causa=causa)
    elif natureza:
        frase = _frase("RC_TERMO_OBITO__natureza", natureza=natureza)
    else:
        return ""
    # O documento do atestante entra cru, depois da vírgula: não tem
    # palavra própria que seja frase, e por isso não é peça.
    return (frase
            + (_frase("RC_TERMO_OBITO__atestante", atestante=atestante)
               if atestante else "")
            + (f", {documento_do_atestante}" if documento_do_atestante else "")
            + ".")


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
    # **O TERMO CONCORDA COM O SEXO DE QUEM FALECEU** — LD01, 21/10/2026.
    # «Filho de», «Sepultado em» e «Era eleitor» eram uma peça só, no
    # masculino, e o termo de uma falecida saía no masculino (LRP art. 80, 3º).
    # Cada uma tem agora a forma feminina ao lado; quem escolhe é o sexo.
    feminino = _feminino(falecido)

    local = _texto(assento.get("local_fato_nome"))
    endereco = _texto(assento.get("local_fato_endereco"))
    if local and endereco:
        local = f"{local}, {endereco}"

    filiacao = _filiacao_qualificada(por_papel.get("MAE"), por_papel.get("PAI"),
                                     CAMPOS_DOS_PAIS_NO_OBITO)
    estado_civil = _texto(falecido.get("estado_civil"))
    numero_do = _texto(assento.get("numero_do"))
    sepultamento = _texto(assento.get("local_sepultamento"))
    testamento = _texto(assento.get("testamento"))

    def _sim(chave: str) -> bool:
        return _texto(marcas.get(chave)) == MO.SIM

    def _nao(chave: str) -> bool:
        return _texto(marcas.get(chave)) == MO.NAO

    # AS TRES FRASES DAS MARCAS. **«Sim» e «nao» sao os dois que se escrevem**;
    # o «nao perguntado» nao vira frase aqui — ele vai para a declaracao do
    # § 1o, que e onde a norma manda que ele apareca. Cada resposta e uma peca
    # do termo (LF06C), e so a que vale e lida.
    def _marca(chave: str, peca_sim: str, peca_nao: str) -> str:
        if _sim(chave):
            return _frase(peca_sim)
        if _nao(chave):
            return _frase(peca_nao)
        return ""

    marca_dos_filhos = _marca("obito_possui_filho", "RC_TERMO_OBITO__filhos_sim",
                              "RC_TERMO_OBITO__filhos_nao")

    return {
        "data_ato_extenso": data_do_termo(assento.get("data_ato")),
        "cidade_do_ato": _texto(sv.get("ri_cidade")),
        "declarante_qualificacao": qualificacao_inteira(
            por_papel.get("DECLARANTE", {})),
        "falecido_qualificacao": (qualificacao_inteira(falecido, nome_negrito=True)
                                  + frase_do_sexo_idade_e_cor(falecido, assento)),
        "data_fato_extenso": data_do_termo(assento.get("data_fato"),
                                           com_numeros=True),
        "frase_hora": _frase_da_hora(assento.get("hora_fato"),
                                     "RC_TERMO_OBITO__hora",
                                     "RC_TERMO_OBITO__hora_cheia"),
        "local_do_fato": local,
        # **AS FRASES SAO INTEIRAS, e comecam depois de um ponto.** O modelo
        # fecha a qualificacao com `.` e abre linha nova; uma frase que
        # comecasse com virgula sairia «lavrador., filho de» — medido no
        # primeiro ensaio desta ponte, em 31/08/2026.
        "frase_filiacao": (_frase("RC_TERMO_OBITO__filiacao_feminino" if feminino
                                  else "RC_TERMO_OBITO__filiacao",
                                  filiacao=filiacao)
                           if filiacao else ""),
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
        #   caso em que a declaracao e obrigatoria. (Ate o LF06C havia aqui um
        #   segundo ramo pelo `documento_numero` do falecido que devolvia vazio
        #   dos dois lados; saiu, e o termo nao mudou.)
        "frase_identificacao": (_frase("RC_TERMO_OBITO__desconhecido")
                                if _sim("obito_desconhecido") else ""),
        "frase_declaracao_de_obito": (
            _frase("RC_TERMO_OBITO__declaracao_de_obito", numero=numero_do)
            if numero_do else ""),
        # A natureza, a causa e quem atestou — ver `frase_da_causa` (LD01).
        "frase_causa": frase_da_causa(assento),
        "frase_sepultamento": (
            _frase("RC_TERMO_OBITO__sepultamento_feminino" if feminino
                   else "RC_TERMO_OBITO__sepultamento", local=sepultamento)
            if sepultamento else ""),
        "frase_eleitor": (
            _marca("obito_eleitor", "RC_TERMO_OBITO__eleitor_sim_feminino",
                   "RC_TERMO_OBITO__eleitor_nao_feminino") if feminino
            else _marca("obito_eleitor", "RC_TERMO_OBITO__eleitor_sim",
                        "RC_TERMO_OBITO__eleitor_nao")),
        "frase_deixou_bens": (_marca("obito_possui_bens",
                                     "RC_TERMO_OBITO__bens_sim",
                                     "RC_TERMO_OBITO__bens_nao")
                              + frase_dos_herdeiros(assento)).strip(),
        "frase_filhos": (frase_dos_filhos_do_falecido(assento, marca_dos_filhos)
                         if _sim("obito_possui_filho") else marca_dos_filhos),
        "frase_testamento": (
            _frase("RC_TERMO_OBITO__testamento", testamento=testamento)
            if testamento else ""),
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
    So calcula. Sem título informado, devolve vazio: não se inventa sentença.

    Cada cláusula com palavra própria é peça de `RC_TERMO_LIVRO_E` (LF06C); o
    « em {data}» e o espaço que separa as cláusulas são cola, e ficam aqui —
    como a decisão de cada uma entrar."""
    tipo = _texto(assento.get("livro_e_titulo")).upper()
    data = data_do_termo(assento.get("livro_e_titulo_data"))
    em_data = f" em {data}" if data else ""
    if tipo == "SENTENCA":
        juiz = _texto(assento.get("livro_e_juiz"))
        juizo = _texto(assento.get("livro_e_juizo"))
        processo = _texto(assento.get("livro_e_processo"))
        transito = data_do_termo(assento.get("livro_e_transito"))
        # Com o juízo, o juiz vem depois dele, entre vírgulas; sem, é o juiz
        # quem profere.
        if juiz and juizo:
            do_juiz = _frase("RC_TERMO_LIVRO_E__juiz_do_juizo", juiz=juiz)
        elif juiz:
            do_juiz = " " + _frase("RC_TERMO_LIVRO_E__juiz", juiz=juiz)
        else:
            do_juiz = ""
        return (_frase("RC_TERMO_LIVRO_E__sentenca") + em_data
                + (" " + _frase("RC_TERMO_LIVRO_E__juizo", juizo=juizo)
                   if juizo else "")
                + do_juiz
                + (_frase("RC_TERMO_LIVRO_E__processo", processo=processo)
                   if processo else "")
                + (_frase("RC_TERMO_LIVRO_E__transito", transito=transito)
                   if transito else ""))
    if tipo == "ESCRITURA":
        livro = _texto(assento.get("livro_e_escritura_livro"))
        folha = _texto(assento.get("livro_e_escritura_folha"))
        tab = _texto(assento.get("livro_e_tabelionato"))
        return (_frase("RC_TERMO_LIVRO_E__escritura") + em_data
                + (" " + _frase("RC_TERMO_LIVRO_E__escritura_livro", livro=livro)
                   if livro else "")
                + (_frase("RC_TERMO_LIVRO_E__escritura_folha", folha=folha)
                   if folha else "")
                + (_frase("RC_TERMO_LIVRO_E__escritura_notas", tabelionato=tab)
                   if tab else ""))
    if tipo == "TERMO":
        return _frase("RC_TERMO_LIVRO_E__termo_declaratorio") + em_data
    return ""


def _filiacao_curta(titular: dict | None, mae: dict | None,
                    pai: dict | None) -> str:
    """«, filho de X e de Y» — só os nomes (art. 94-A, III), na ordem da casa
    (a filiação 1 primeiro). So calcula. «filho»/«filha» concorda com o sexo
    do titular: é a regra que escolhe a peça."""
    nomes = [n for n in (_texto((mae or {}).get("nome")),
                         _texto((pai or {}).get("nome"))) if n]
    if not nomes:
        return ""
    return _frase("RC_TERMO_LIVRO_E__filha_de" if _feminino(titular)
                  else "RC_TERMO_LIVRO_E__filho_de", nomes=" e de ".join(nomes))


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

    **O TEXTO DE CADA PEDAÇO É PEÇA DE `RC_TERMO_LIVRO_E`** (LF06C): a cabeça
    de cada espécie («Interdição decretada») e cada cláusula com palavra
    própria. A espécie que escolhe as cláusulas, o sexo que escolhe «nomeado
    curador» ou «nomeada curadora» e o ponto que fecha a frase ficam aqui.
    """
    a = assento or {}
    t = por_papel.get("REGISTRADO") or {}
    titulo = _do_titulo(a)
    pelo = f" {titulo}" if titulo else ""
    nasc = _texto(a.get("livro_e_registro_nascimento"))
    cas = _texto(a.get("livro_e_registro_casamento"))
    conj = _texto(a.get("livro_e_conjuge"))

    def reg_nasc() -> str:
        return (_frase("RC_TERMO_LIVRO_E__nascimento_registrado", registro=nasc)
                if nasc else "")

    def reg_cas() -> str:
        return ((_frase("RC_TERMO_LIVRO_E__casado_com", conjuge=conj)
                 if conj else "")
                + (_frase("RC_TERMO_LIVRO_E__casamento_registrado", registro=cas)
                   if cas else ""))

    def cabeca(peca: str) -> str:
        return " " + _frase(peca) + pelo

    def q(papel: str) -> str:
        return qualificacao_inteira(por_papel.get(papel) or {})

    def tem_nome(papel: str) -> bool:
        p = por_papel.get(papel)
        return bool(p and _texto(p.get("nome")))

    def nomeado(papel: str, peca_masc: str, peca_fem: str) -> str:
        if not tem_nome(papel):
            return ""
        return _frase(peca_fem if _feminino(por_papel.get(papel)) else peca_masc,
                      qualificacao=q(papel))

    def limites_da_curatela() -> str:
        limites = _texto(a.get("livro_e_limites"))
        return (_frase("RC_TERMO_LIVRO_E__limites", limites=limites)
                if limites else "")

    def filiacao() -> str:
        return _filiacao_curta(t, por_papel.get("MAE"), por_papel.get("PAI"))

    if especie == "EMANCIPACAO":
        tutela = (_frase("RC_TERMO_LIVRO_E__representado_pelo_tutor",
                         qualificacao=q("TUTOR"))
                  if tem_nome("TUTOR") else "")
        return (cabeca("RC_TERMO_LIVRO_E__emancipacao") + reg_nasc()
                + filiacao() + tutela + ".")
    if especie == "INTERDICAO":
        causa = _texto(a.get("livro_e_causa"))
        intern = _texto(a.get("livro_e_internacao"))
        return (cabeca("RC_TERMO_LIVRO_E__interdicao") + reg_nasc() + reg_cas()
                + (_frase("RC_TERMO_LIVRO_E__requerimento",
                          requerente=q("REQUERENTE"))
                   if tem_nome("REQUERENTE") else "")
                + (_frase("RC_TERMO_LIVRO_E__causa", causa=causa)
                   if causa else "")
                + nomeado("CURADOR", "RC_TERMO_LIVRO_E__curador_nomeado",
                          "RC_TERMO_LIVRO_E__curadora_nomeada")
                + limites_da_curatela() + "."
                + (" " + _frase("RC_TERMO_LIVRO_E__internacao", local=intern)
                   if intern else ""))
    if especie == "AUSENCIA":
        tempo = _texto(a.get("livro_e_ausencia_tempo"))
        return (cabeca("RC_TERMO_LIVRO_E__ausencia") + reg_nasc() + reg_cas()
                + (_frase("RC_TERMO_LIVRO_E__tempo_de_ausencia", tempo=tempo)
                   if tempo else "")
                + (_frase("RC_TERMO_LIVRO_E__promovido_por",
                          requerente=q("REQUERENTE"))
                   if tem_nome("REQUERENTE") else "")
                + nomeado("CURADOR", "RC_TERMO_LIVRO_E__curador_nomeado",
                          "RC_TERMO_LIVRO_E__curadora_nomeada")
                + limites_da_curatela() + ".")
    if especie == "TUTELA":
        return (cabeca("RC_TERMO_LIVRO_E__tutela") + reg_nasc() + filiacao()
                + nomeado("TUTOR", "RC_TERMO_LIVRO_E__tutor_nomeado",
                          "RC_TERMO_LIVRO_E__tutora_nomeada") + ".")
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
        frase = (" " + _frase("RC_TERMO_LIVRO_E__uniao_estavel")
                 + (f" entre {', e '.join(lados)}" if lados else "")
                 + (_frase("RC_TERMO_LIVRO_E__reconhecida") + pelo
                    if titulo else "")
                 + (_frase("RC_TERMO_LIVRO_E__inicio", data=inicio)
                    if inicio else "")
                 + (_frase("RC_TERMO_LIVRO_E__regime", regime=regime)
                    if regime else "") + ".")
        if nasc:
            frase += " " + _frase("RC_TERMO_LIVRO_E__registros_de_nascimento",
                                  registros=nasc)
        if cas:
            frase += " " + _frase("RC_TERMO_LIVRO_E__anteriores", anteriores=cas)
        for c in (c1, c2):
            if c and _texto(c.get("nome_pos")) and \
                    _texto(c.get("nome_pos")) != _texto(c.get("nome")):
                frase += " " + _frase("RC_TERMO_LIVRO_E__novo_nome",
                                      nome=_texto(c.get("nome")),
                                      nome_pos=_texto(c.get("nome_pos")))
        return frase
    if especie == "OPCAO_NACIONALIDADE":
        return (cabeca("RC_TERMO_LIVRO_E__opcao_nacionalidade") + reg_nasc()
                + filiacao() + ".")
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


# As constantes de texto que viraram PEÇA no LF06C, e a peça que responde
# pelo nome antigo. Os papéis inteiros (`TERMO_*`, `QUALIFICACAO`) respondem
# pelo catálogo, em `modelos_da_casa.constante_antiga`.
_PECAS_DE_ANTES = {
    "FRASE_PRIMEIRO_REGISTRO": "RC_TERMO_NASCIMENTO__primeiro_registro",
}


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`;
    as frases e a ordem da qualificação saíram no LF06C. Quem ainda importa o
    nome antigo recebe o padrão da base — o MESMO que o papel imprime, e não
    uma cópia que ficou para trás. Nome que não é de papel continua sendo
    `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    if nome in _PECAS_DE_ANTES:
        return _MODELOS.padrao_de(_PECAS_DE_ANTES[nome])
    return _MODELOS.constante_antiga(__name__, nome)

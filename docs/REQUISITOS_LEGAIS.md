# Requisitos legais dos termos e das certidões, por atribuição

Pedido do oficial (20/10/2026): «os modelos têm de abarcar o que a LEI e as
NORMAS exigem». Cada atribuição tem a sua seção, escrita pelo lote dela; cada
elemento traz o artigo. Fontes, na ordem de prevalência: Lei 6.015/1973 (LRP)
e as leis da atribuição, o Código Nacional de Normas (Prov. CNJ 149/2023 e
alterações, «CNN») e o Código de Normas Extrajudicial do MA (Prov. COGEX
28/2026, «CN-MA»). Os textos estão em `migracao-pg/referencia/`.

## Registro Civil das Pessoas Naturais (LT01)

Executável em `tests/test_requisitos_rcpn.py` — a chave entre colchetes é o
`id` da linha da matriz (`MATRIZ`). O caminho pelas telas, com protocolo, selo
e papel, está em `tests/test_fluxo_rcpn.py`. Textos da LRP e do CNN em
`migracao-pg/referencia/normas/`.

Cada linha diz o elemento obrigatório, o artigo e se o modelo da casa
(`modelos_padrao/rcpn/`) o cumpre: **✓** cumpre (teste verde) · **✗ DEFEITO**
o modelo não tem (teste `xfail(strict=True)`) · **conferir** o texto oficial
não estava no disco ou há conflito entre as fontes. **✓ LD01** é o defeito que
o LD01 (21/10/2026, «corrija tudo») consertou: o `xfail` saiu e o teste passa.

### Assento de nascimento — Livro A (`RC_TERMO_NASCIMENTO`)

| Elemento | Fonte | Modelo |
|---|---|---|
| dia, mês, ano e lugar do nascimento e a hora certa ou aproximada | LRP art. 54, 1º; CN-MA art. 233, I | ✓ [nasc.data_hora_lugar] |
| sexo do registrando | LRP art. 54, 2º; CN-MA art. 233, II (sexo «ignorado»: CNN art. 525) | ✓ [nasc.sexo] |
| o fato de ser gêmeo, e a ordem de nascimento | LRP art. 54, 3º, e art. 63; CN-MA art. 234 | ✓ LD01 [nasc.gemeo] — o parto múltiplo informado no balcão (`ibge_gemeo`) e a ordem (`gemeo_ordem`) vão ao termo, concordando com o sexo (`rc_modelos_do_livro.frase_dos_gemeos`) |
| nome e prenome postos à criança (ao menos um sobrenome de ascendente) | LRP art. 54, 4º, e art. 55; CNN art. 515-B | ✓ [nasc.nome] |
| declaração de que nasceu morta, ou morreu no ato ou logo depois do parto | LRP art. 54, 5º; CN-MA art. 233, V | ver natimorto |
| ordem de filiação de irmãos do mesmo prenome | LRP art. 54, 6º | conferir — o CN-MA art. 233, § 1º, veda «a ordem de filiação» no termo e na certidão |
| nomes, naturalidade e profissão dos pais; domicílio ou residência | LRP art. 54, 7º; CN-MA art. 233, VI e VII; CN-MA art. 229, § 3º (endereço completo) | ✓ [nasc.pais] |
| lugar e cartório onde os pais se casaram | LRP art. 54, 7º | conferir — o modelo escreve («casados entre si em…»), e o CN-MA art. 233, § 1º, veda o estado civil dos pais no termo; a certidão o omite (CN-MA art. 379) |
| idade da genitora na ocasião do parto | LRP art. 54, 7º | ✓ [nasc.idade_da_mae] |
| nomes e prenomes dos avós paternos e maternos | LRP art. 54, 8º; CN-MA art. 233, VIII | ✓ [nasc.avos] |
| duas testemunhas (nome, profissão, residência, documento), no parto sem assistência médica fora de hospital | LRP art. 54, 9º; CN-MA art. 233, IX | ✓ LD01 [nasc.testemunhas] — claro `{testemunhas}`, cada uma qualificada; a tela ganhou a 2ª testemunha (no nascimento, o papel `TESTEMUNHA2` — LH05) |
| número da DNV, com dígito verificador (salvo registro tardio) | LRP art. 54, 10; CN-MA arts. 233, X, e 236 | ✓ [nasc.dnv] |
| registro fora do prazo (tardio): à vista do requerimento autuado e numerado, assinado por duas testemunhas que atestam, sob as penas da lei, a identidade do registrando | LRP art. 46; CN-MA art. 249, I e II; CNN arts. 480 a 494 | ✓ LH05 [nasc.tardio] — claro `{frase_tardio}` (hotfixes do servidor de 21/10/2026); no tardio as testemunhas saem uma vez só, na frase dele |
| a dispensa das testemunhas só com o registrando menor de 12 anos **e** com DNV | CN-MA art. 249, II | ✓ LH05 [nasc.tardio_dispensa] — calculada (`rc_assento.regra_das_testemunhas_do_tardio`), e não impressa em toda folha como no modelo do E-Ofício |
| naturalidade do registrando (município do parto ou da residência da mãe) | LRP art. 54, 11, e § 4º; CNN art. 474; CN-MA art. 233, XI | ✓ [nasc.naturalidade] |
| CPF do registrando | CN-MA art. 233, XII; CNN art. 477, § 1º | ✓ [nasc.cpf] |
| leitura, assinatura do declarante e subscrição do oficial | LRP arts. 37 e 38; CN-MA art. 212 | ✓ [nasc.encerramento] |
| matrícula (32 dígitos) | CNN art. 473 | ✓ [nasc.matricula] |
| selo «no corpo do ato» | CN-MA arts. 130 e 131 | ✓ na folha do livro (carimbo com QR) — `test_fluxo_rcpn` |

### Natimorto — Livro C-Auxiliar (pelo mesmo `RC_TERMO_NASCIMENTO`)

| Elemento | Fonte | Modelo |
|---|---|---|
| registro no C-Auxiliar «com os elementos que couberem» | LRP art. 53, § 1º; CNN art. 479-A; CN-MA art. 210, V | ✓ (série RC_C_AUXILIAR) |
| a declaração de que nasceu morta | LRP art. 53, § 1º, e art. 54, 5º | ✓ LD01 [nati.nasceu_morta] — claro `{frase_natimorto}`: «nasceu morta uma criança», com a Declaração de Óbito no lugar da DNV |
| nome facultativo, a critério dos pais | LRP art. 53, § 3º; CNN art. 479-A | conferir — a tela exige o nome |
| sem CPF | CNN art. 479-A, § 1º | ✓ (o natimorto não tem o bloco do CPF) |
| registro e 1ª certidão gratuitos | LRP art. 30; CN-MA art. 217 | ✓ (14.d isento) |

### Assento de óbito — Livro C (`RC_TERMO_OBITO`)

| Elemento | Fonte | Modelo |
|---|---|---|
| hora, dia, mês e ano do falecimento | LRP art. 80, 1º; CN-MA art. 255, I | ✓ [ob.data_hora] |
| lugar do falecimento, com indicação precisa | LRP art. 80, 2º; CN-MA art. 255, II | ✓ [ob.lugar] |
| nome, sexo, estado, profissão, naturalidade, domicílio e residência | LRP art. 80, 3º; CN-MA art. 255, III | ✓ [ob.falecido] · ✓ LD01 concordância de gênero («Filha de», «Sepultada», «Era eleitora» — peças `_feminino`) e o sexo escrito — `test_fluxo_rcpn` |
| idade, data do nascimento e cor | LRP art. 80, 3º; CN-MA art. 255, III | ✓ LD01 [ob.idade_e_cor] — «com 76 anos de idade, de cor parda», pela régua da casa (`rc_assento.idade_na_data`) |
| cônjuge sobrevivente ou pré-morto e o cartório do casamento | LRP art. 80, 4º; CN-MA art. 255, IV | ✓ [ob.conjuge] |
| se era eleitor | LRP art. 80, 11º; CN-MA art. 255, V | ✓ [ob.eleitor] |
| nomes dos pais | LRP art. 80, 5º; CN-MA art. 255, VI | ✓ [ob.pais_nomes] |
| profissão, naturalidade e residência dos pais | LRP art. 80, 5º; CN-MA art. 255, VI | ✓ LD01 [ob.pais_qualificacao] — os nomes e, entre parênteses, «respectivamente», a qualificação de cada um |
| se faleceu com testamento conhecido | LRP art. 80, 6º; CN-MA art. 255, VII | ✓ [ob.testamento] |
| se deixou filhos, nome e idade de cada um | LRP art. 80, 7º; CN-MA art. 255, VIII | ✓ [ob.filhos] |
| causa conhecida e o nome dos atestantes | LRP art. 80, 8º; CN-MA art. 255, IX | ✓ [ob.causa] |
| se a morte foi natural ou violenta | LRP art. 80, 8º; CN-MA art. 255, IX | ✓ LD01 [ob.natural_ou_violenta] — «A morte foi natural/violenta», da natureza informada (`ibge_natureza_obito`) |
| lugar do sepultamento | LRP art. 80, 9º; CN-MA art. 255, X | ✓ [ob.sepultamento] |
| se deixou bens e herdeiros menores ou interditos | LRP art. 80, 10º; CN-MA art. 255, XI | ✓ [ob.bens_herdeiros] |
| ao menos um documento (CPF, RG, título, PIS, registro de nascimento…) | LRP art. 80, 12º; CN-MA art. 255, XII | ✓ [ob.documento] |
| o que não se pôde constar: «fez a pergunta e o declarante ignorava» | CN-MA art. 255, § 1º | ✓ — consertado no LT01: «pessoa não identificada» não é item do artigo e saiu da declaração |
| desconhecido: estatura, cor, sinais, idade presumida, vestuário | LRP art. 81; CN-MA art. 257 | conferir — peça `__desconhecido` só diz que não se identificou |
| leitura e assinatura do declarante e do oficial | LRP arts. 37, 38 e 82 | ✓ [ob.encerramento] |

### Assento de casamento — Livro B (`RC_TERMO_CASAMENTO`)

| Elemento | Fonte | Modelo |
|---|---|---|
| nomes, nacionalidade, naturalidade, data de nascimento, profissão, domicílio dos cônjuges | LRP art. 70, 1º; CN-MA art. 284, I | ✓ [cas.conjuges] |
| nomes dos pais | LRP art. 70, 2º; CN-MA art. 284, II | ✓ [cas.pais_nomes] |
| nacionalidade, data de nascimento ou de morte e residência dos pais | LRP art. 70, 2º; CN-MA art. 284, II | ✓ LD01 [cas.pais_qualificacao] — os nomes e a nacionalidade, a data de nascimento e a residência de cada um |
| cônjuge precedente e data da dissolução | LRP art. 70, 3º; CN-MA art. 284, III | ✓ [cas.casamento_anterior] |
| data da publicação dos proclamas — habilitação de outra serventia | LRP art. 70, 4º; CN-MA art. 284, IV | ✓ [cas.proclamas_de_fora] |
| data da publicação dos proclamas — habilitação desta serventia | LRP art. 70, 4º | ✓ LD01 [cas.proclamas_desta_casa] — a data do edital da habilitação desta casa, achada pela tela de lavrar (`rc_termo._habilitacao_desta_casa`) |
| data da celebração | LRP art. 70, 4º | ✓ LD01 — claro `{frase_da_celebracao}` (`test_o_termo_de_casamento_traz_a_data_da_celebracao`) · conferir: o termo começa «Em <data do ato>»; ver as perguntas do LD01 |
| relação dos documentos apresentados | LRP art. 70, 5º; CN-MA art. 284, V | ✓ [cas.documentos] |
| nomes das testemunhas (pelo menos duas; quatro ou sete nos casos do CN-MA art. 277) | LRP art. 70, 6º e parágrafo único; CC art. 1.534 | ✓ no modelo [cas.testemunhas_nomes] · ✓ LD01 na tela: a 2ª gaveta (`test_o_casamento_registra_as_duas_testemunhas`) |
| nacionalidade, profissão, domicílio e residência das testemunhas | LRP art. 70, 6º; CN-MA art. 284, VI | ✓ LD01 [cas.testemunhas_qualificacao] |
| regime de bens, com data e cartório do pacto antenupcial | LRP art. 70, 7º; CN-MA art. 284, VII | ✓ [cas.regime_e_pacto] |
| nomes que os cônjuges passam a ter | LRP art. 70, 8º; CN-MA art. 284, VIII | ✓ [cas.nome_adotado] |
| filhos havidos de matrimônio anterior; impressão digital de quem não assina | LRP art. 70, 9º e 10º | conferir — o CN-MA art. 284 os omite; o modelo não os tem |
| leitura e assinaturas do presidente, cônjuges, testemunhas e oficial | LRP art. 70, caput; CN-MA art. 282 | ✓ [cas.encerramento] |
| religioso com efeito civil: data, lugar, culto, celebrante e qualidade, cartório da habilitação | LRP art. 73, § 1º; CN-MA arts. 293 e 297 | conferir — sem teste; o B-Auxiliar usa o mesmo modelo do civil |
| conversão de união estável: menção de que é conversão, registro anterior da união | LRP art. 70-A, § 4º; CNN art. 549 | conferir — a variante `CONVERSAO` do modelo não tem texto |

### Habilitação, proclamas e certidão de habilitação

| Elemento | Fonte | Modelo |
|---|---|---|
| edital: nome, estado civil, filiação, cidade e circunscrição do domicílio dos noivos | CNN art. 122; LRP art. 67, § 1º | ✓ LD01 [edital.proclamas] — `{estado_civil}`, `{filiacao}`, `{domicilio}` (só a cidade, e «nesta circunscrição» quando é a da serventia — o «tão somente» do art. 122 vale dos dois lados) |
| registro do edital no Livro D, com a época da publicação e os documentos | LRP arts. 43 e 44; CN-MA arts. 265 a 267 | ✓ LD01 — o edital se registra no Livro D ao ser publicado (`habilitacao.registrar_o_edital_no_livro_d`), e o selo da habilitação o leva (`test_casamento_pela_habilitacao_desta_casa_vai_do_protocolo_a_certidao`) |
| certidão de habilitação: nubentes, regime, edital, validade de 90 dias, quem assina | CC arts. 1.531 e 1.532; LRP art. 67, § 1º; CN-MA art. 272 | ✓ [cert.habilitacao] |

### Livro E (`RC_TERMO_LIVRO_E`, um modelo para as seis espécies)

| Elemento | Fonte | Modelo |
|---|---|---|
| emancipação: data do registro e do título; emancipado (nome, idade, filiação, profissão, naturalidade, residência); data e cartório do nascimento; pais ou tutor; escritura com data, livro, folha e ofício | LRP art. 90, 1º a 3º; CN-MA art. 329 | ✓ [e.emancipacao] |
| interdição: sentença (data, juiz, vara), curador, requerente e causa, limites, internação, nascimento e casamento | LRP art. 92, 1º a 7º; CN-MA art. 328 | ✓ [e.interdicao] |
| ausência: sentença, tempo de ausência, curador e limites da curatela | LRP art. 94; CN-MA art. 328 | ✓ [e.ausencia] · conferir o «nome do promotor do processo» (art. 94, 4º): não há campo |
| união estável: companheiros, título (escritura: data, livro, folha, tabelionato), regime, início | LRP art. 94-A; CNN arts. 537 a 539 | ✓ [e.uniao_estavel] |
| opção de nacionalidade: sentença do juízo federal | LRP art. 32, § 4º; CN-MA art. 327, IV | ✓ (pela tela, `test_fluxo_rcpn`) · conferir: elementos do assento não estão nos textos |
| tutela | LRP art. 92, por analogia | ✓ (pela tela) |
| traslado de assento lavrado no exterior; morte presumida; tomada de decisão apoiada | LRP art. 32 e art. 88; CN-MA arts. 307 a 329 | conferir — não modelados |

### Averbação, anotação e retificação

| Elemento | Fonte | Modelo |
|---|---|---|
| averbação de sentença: data, processo, data da sentença, juiz e vara, determinação, trânsito | CN-MA art. 341; LRP arts. 99 e 100 | conferir — o teor é digitado no balcão (há modelo só para a retificação de erro material, `RC_AVERBACAO_RETIFICACAO`) |
| demais averbações: data, o ato que a determinou, a alteração | CN-MA art. 343 | ✓ pela tela (teor + fundamento + quem lavrou + selo) |
| anotação: data, registro ou averbação promovida, serventia, livro, folha e número | LRP art. 106; CN-MA art. 369 | ✓ pela tela |
| retificação administrativa: protocolo, data, fundamento | LRP art. 110; CN-MA arts. 352 e 355 | ✓ pela tela (fundamento obrigatório) |

### Certidões (`RC_CERTIDAO_RESUMO`, `RC_CERTIDAO_INTEIRO_TEOR`, molde ODT do CNJ)

| Elemento | Fonte | Modelo |
|---|---|---|
| breve relato de nascimento: nome, matrícula, data por extenso, hora, naturalidade, local do parto, sexo, filiação, avós, gêmeo, DNV, data do registro, livro/folha/termo | LRP art. 19, § 4º; CNN arts. 473 a 476 | ✓ [cert.nasc] |
| CPF na certidão | CNN art. 477 | ✓ [cert.cpf] |
| serventia, lugar, data e fé | LRP art. 19; CN-MA arts. 378 e 381 | ✓ [cert.fe] · papel: CNS, município, oficial e função — `test_fluxo_rcpn` |
| breve relato de óbito: nome, CPF, matrícula, data e hora, sexo, idade, estado civil, cor, naturalidade, domicílio, local, DO, causa e atestante, sepultamento, filiação | CNN arts. 472, 473 e 477; LRP art. 80 | ✓ [cert.obito] |
| óbito: eleitor, bens e filhos que o termo declara | LRP art. 21 c/c art. 80 | ✓ LD01 [cert.obito_eleitor_bens_filhos] · papel: cônjuge, bens e filhos consertados no LT01; ✓ LD01 o município do falecimento (`test_o_papel_da_certidao_de_obito_traz_o_municipio_do_falecimento`) |
| breve relato de casamento: nomes, matrícula, data, regime, nomes adotados, nascimento, estado civil anterior e filiação de cada cônjuge | LRP art. 70; CNN arts. 472 e 473 | ✓ [cert.casamento] |
| natimorto | LRP art. 53; CNN art. 479-A | ✓ breve relato [cert.natimorto] · ✓ LD01 papel próprio |
| Livro E: espécie, título registrado, curador, limites | LRP arts. 19, 21 e 89 a 94-A | ✓ LD01 [cert.livro_e] — breve relato com a espécie, o título, o curador/tutor/companheiros e os limites (`rc_certidao.linhas_do_livro_e`), e papel próprio |
| as averbações, mencionadas obrigatoriamente | LRP art. 21; CN-MA art. 386 | ✓ [cert.averbacao] |
| a inscrição «a presente certidão envolve elementos de averbação à margem do termo» | LRP art. 21, parágrafo único | ✓ LD01 [cert.inscricao_do_art_21] — peça `RC_CERTIDAO_RESUMO__envolve_averbacao`, no teor e no papel, quando há averbação ou retificação |
| inteiro teor: serventia (CNS, município), espécie, nome, matrícula, livro, folha e termo, e a reprodução do termo | LRP art. 19, § 1º; CNN art. 473; CN-MA art. 378 | ✓ [cert.inteiro_teor] + reprodução palavra por palavra (`test_fluxo_rcpn`) |
| selo no corpo do ato, com consulta pelo código ou pelo QR | CN-MA arts. 130 a 132 | ✓ papel com o código, o endereço de consulta e o QR do próprio selo (`test_fluxo_rcpn`) · conferir a URL e o QR no regulamento do selo do TJMA (não está no disco) |
| selo de categoria «isento» ou «gratuito» | CN-MA art. 133 | ✓ envelope `isentoGratuito` = ISENTO (14.a, 14.c, 14.d) ou GRATUITO com o motivo |
| emolumentos no próprio documento | LRP art. 14, parágrafo único; CN-MA art. 87, XVI | ✓ pelo texto do selo do TJMA, decomposto no papel (`selo_no_papel`) — conferido com a etiqueta na forma da do TJMA |
| gratuidade sem expressão de pobreza | LRP art. 30, § 4º; CN-MA art. 217, § 3º | ✓ (o papel não escreve o motivo) |
| certidão negativa, com o código (hash) da consulta à CRC | CNN art. 238; CN-MA art. 385 | ✗ não existe no RCPN |
| modelos nacionais (Anexos IV a VII do CNN, Prov. 182/2024) | CNN art. 472 | conferir — o arquivo baixado traz só o título dos anexos |

### Conflitos entre as fontes, para o oficial decidir

1. Ordem de filiação e lugar/cartório do casamento dos pais: a LRP art. 54, 6º e
   7º, manda constar; o CN-MA art. 233, § 1º, veda o estado civil dos pais e a
   ordem de filiação no termo e na certidão. O termo da casa escreve o
   casamento dos pais; a certidão o omite (CN-MA art. 379).
2. Algarismos: a LRP art. 35 proíbe; o CN-MA art. 212, II, manda escrever por
   extenso e repetir em algarismos entre parênteses (é o que o termo faz).
3. Regime de bens que exige a menção do pacto: «comunhão ou o legal» (LRP art.
   70, 7º) × «comunhão parcial ou o obrigatoriamente estabelecido» (CN-MA art.
   284, VII).
4. Óbito fora do prazo: a LRP art. 78 remete aos prazos do art. 50; o CN-MA
   art. 258 exige determinação judicial (a casa avisa e não trava).
5. Data de início da união estável na conversão: LRP art. 70-A, § 6º, e CNN
   art. 549, III × CN-MA art. 303, parágrafo único.

## Caixa e protocolo geral (LT06)

O caixa não lavra termo em livro de ato: o que ele escreve na casa é o
**lançamento** (`cx_lancamentos`, um por serviço, com os fundos separados) e a
linha do **Livro de Controle de Depósito Prévio**; o que sai com o cliente é o
**recibo**, o **comprovante de recepção** e o **orçamento**. O teste é
`tests/test_requisitos_caixa.py` (a matriz abaixo, papel montado com contexto
completo + marcador no padrão `modelos_padrao/caixa/`); o fluxo pelas telas é
`tests/test_fluxo_caixa.py`.

Não há, no CN-MA nem no CNN, um artigo que liste os elementos do recibo; a
lista sai dos dispositivos abaixo, e o que é prática da casa (e não exigência)
está marcado assim.

### Recibo dos emolumentos (`CAIXA_RECIBO`)

| Elemento | Base |
|---|---|
| Dar recibo dos emolumentos percebidos | CN-MA art. 87, IX; Lei 8.935/1994, art. 30, IX |
| Valor de cada ato no próprio documento | LRP art. 14, parágrafo único; CN-MA art. 87, XVI |
| Discriminação das parcelas: emolumentos e cada fundo (FERJ/FERC, FADEP, FEMP, FERRFIS) | CN-MA art. 12, IV; art. 881, § 1º; art. 952; Lei 9.492/1997, art. 37, § 2º |
| Número e data do recibo | CN-MA art. 115, II (inventário pede «número e data do último recibo») |
| Quem pagou, o valor e por extenso | CN-MA art. 87, IX (prática da casa: extenso contra adulteração) |
| Protocolo a que se refere | CN-MA art. 33 (o pedido tem protocolo) |
| Forma de pagamento (cheque: identificação do cheque) | CN-MA art. 927, parágrafo único |
| Identificação da serventia, local, data e quem emitiu | prática da casa (o CN-MA não lista; art. 12, II — o corregedor fiscaliza a «extração de recibos») |
| Recibo do DEPÓSITO PRÉVIO com a discriminação orçamentária de todos os valores previstos | CN-MA art. 197 — ✓ consertado no LD06: o recibo do lançamento do depósito traz o orçamento congelado no depósito, item a item com os fundos, sob «DISCRIMINAÇÃO ORÇAMENTÁRIA», e diz que é orçamento e não pagamento de ato (art. 202). Depósito registrado sem serviço nem protocolo sai sem a discriminação, com aviso na tela e a falta no livro |

### Comprovante de recepção / recibo de protocolo (`CAIXA_RECEPCAO`)

| Elemento | Base |
|---|---|
| Posição do pedido na ordem de atendimento (número), com data e hora | CN-MA art. 33 |
| Data da apresentação, número de ordem e dia previsto para a entrega | CN-MA art. 447, § 4º (RI), art. 974, § 1º (RTD); LRP arts. 153 e 175 |
| Apresentante e natureza do que foi apresentado | LRP art. 175, III e IV; CN-MA art. 894 (Protesto) |
| Valores previstos e o que falta pagar | LRP art. 14, parágrafo único; CN-MA art. 197 |
| Dados pessoais mascarados no papel que viaja | Lei 13.709/2018, art. 6º, III |

### Orçamento / mero cálculo (`CAIXA_ORCAMENTO`)

| Elemento | Base |
|---|---|
| Aviso de que é cálculo, sem prática de ato nem prenotação | LRP art. 12, parágrafo único; CN-MA art. 450, § 5º |
| Cada ato com código, base de cálculo e total; composição dos fundos | CN-MA art. 87, VII-VIII; art. 88, II; CNN art. 228-U, IV (Serp: valores prévios e discriminados) |
| Total por extenso e vigência da tabela | CN-MA art. 87, VII (tabela vigente) |

### Livro de Controle de Depósito Prévio (`/livros-obrigatorios/deposito-previo`)

| Elemento | Base |
|---|---|
| I — número do protocolo do título ou do pedido | CN-MA art. 198, I; CNN art. 188 |
| II — data do depósito | CN-MA art. 198, II |
| III — valor depositado | CN-MA art. 198, III |
| IV — data da conversão em emolumentos, com o ato praticado | CN-MA art. 198, IV; art. 202 |
| V — data da devolução, com a justificativa | CN-MA art. 198, V; arts. 454 a 456 |
| VI — descrição completa do orçamento, com os acréscimos | CN-MA art. 198, VI; art. 881, § 1º (os acréscimos são os fundos) — ✓ consertado no LD06 (`cx_depositos.orcamento`: os itens do protocolo do orçamento, ou o serviço pela tabela vigente, com os emolumentos e cada fundo; o depósito sem orçamento continua com a falta dita no livro) |
| Escrituração só eletrônica | CN-MA art. 196; CNN art. 188, parágrafo único |

### Selo e gratuidade, em todo ato que o caixa cobre

| Regra | Base |
|---|---|
| Nenhum ato sujeito a selo se conclui sem o selo gerado antes | CN-MA art. 130, § 2º |
| O selo consta do corpo do ato (ou dos metadados) | CN-MA art. 131 |
| Consulta pública pelo código ou pelo QR Code | CN-MA art. 132 |
| Ato isento ou gratuito usa selo de categoria própria | CN-MA art. 133 |
| Selo pago só com protocolo e pagamento registrado | ordem do oficial (19/10/2026); não há artigo geral — no Protesto, CN-MA art. 881, § 1º (selo no pagamento, desistência ou cancelamento) |
| Gratuidade presumida: registro de nascimento e de óbito e a 1ª certidão | LRP art. 30, caput; CN-MA art. 217 |
| Pobreza declarada pelo interessado (comprovante arquivado pela casa) | LRP art. 30, §§ 1º e 2º; CN-MA art. 822, § 6º; CNN art. 239, § 5º |
| NFS-e | sem regra no CN-MA nem no CNN; CN-MA art. 190, I, l (ISSQN no Livro Diário) e art. 951, § 8º — conferir na lei do município |
# Requisitos legais dos atos e das certidões

Cada atribuição tem a sua seção, escrita pelo lote que a mediu. A seção diz,
para cada tipo de ato e de certidão, os ELEMENTOS OBRIGATÓRIOS, o artigo que os
exige e se o modelo da casa os tem.

## Tabelionato de Notas (LT02)

Pedido do oficial, 20/10/2026: «TODOS os atos precisam ter uma certidão
adequada» — «TERMO E CERTIDÃO». Os modelos têm de abarcar o que a lei e as
normas exigem.

**A MATRIZ MORA NO TESTE.** A tabela abaixo é a `MATRIZ` de
`tests/test_requisitos_notas.py`, escrita por extenso. O teste monta cada papel
com um contexto completo — a minuta como a tela «Preencher a partir do modelo»
a monta (todos os campos, todas as cláusulas «SE» ligadas), a certidão como
`notas_certidao.emitir` a monta — e confere, para cada elemento, o rótulo e o
valor no papel e, na minuta, que o campo existe no padrão. Mudou a matriz,
muda esta seção; `test_o_documento_da_matriz_descreve_cada_tipo_desta_matriz`
confere que cada tipo de lá tem o seu título aqui.

**COMO LER.** ✓ o modelo tem o elemento e o teste o confere. ✗ o modelo não o
tem: é DEFEITO do modelo, e o caso está marcado `xfail(strict=True)` com o
artigo — consertado o modelo, o teste avisa (XPASS) e a marca sai.

**FONTES, NA ORDEM DE PREVALÊNCIA** (a do pedido): Lei 6.015/1973 e leis da
atribuição; o Código Nacional de Normas (Prov. CNJ 149/2023, texto atualizado
em `referencia/normas/cnn_prov_149_2023.txt`); o Código de Normas do MA (Prov.
COGEX 28/2026, `referencia/codigo_de_normas_extrajudicial_ma.txt`). A Lei
6.015 foi lida em `referencia/normas/lei_6015_compilada.txt`. **Conferir no
texto oficial:** os artigos do Código Civil, da Lei 7.433/1985, da Lei
8.213/1991, da Lei 8.935/1994 e da Lei 9.514/1997 foram citados sem o texto na
pasta `referencia/normas/` — marcados assim na tabela quando o artigo pesa no
elemento.

### O que vale para todo ato das Notas

| Elemento | Fonte | Onde está | Conferido em |
|---|---|---|---|
| selo de fiscalização no corpo do ato, com o código | CN-MA arts. 130 e 131 | moldura: `@@SELO@@` de NOTAS_TERMO_LIVRO, NOTAS_TRASLADO, NOTAS_CARTAO_FICHA; `e.selo` da etiqueta | matriz (o claro) e `tests/test_fluxo_notas.py` (o papel de verdade) |
| QR e endereço da consulta pública do selo | CN-MA art. 132 | carimbo do selo (`ri_odt.carimbo_*`), da etiqueta (`e.qr`) | `tests/test_fluxo_notas.py` |
| emolumentos no próprio documento | CN-MA art. 87, XVI | o carimbo lê o texto que o aparelho devolve (`Total R$ … Emol R$ …`) | `tests/test_fluxo_notas.py` |
| identificação de quem pratica o ato | CN-MA arts. 798, XIII, e 861, § 10 | «perante mim, {{ lavrado_nome }}, {{ lavrado_titulo }}» nas minutas; `e.oficial` na etiqueta; `emitida_por` na certidão | matriz e `tests/test_fluxo_notas.py` |
| identificação da serventia | CN-MA art. 180 | cabeçalho do termo, do traslado, da ficha e da certidão (moldura da rota) | matriz (termo e traslado) e `tests/test_fluxo_notas.py` |

O que é MOLDURA (o cabeçalho e o carimbo que a rota acrescenta) não é modelo da
casa e não entra nesta matriz como modelo: confere-se no papel emitido pelas
telas, em `tests/test_fluxo_notas.py`.

### Conflitos de norma e perguntas ao oficial

- **Endereço eletrônico e filiação na qualificação.** O CN-MA art. 798, V,
  pede filiação e endereço eletrônico; o CNN art. 111 (proteção de dados)
  manda pôr o documento de identificação — e a filiação só na falta dele — e
  DISPENSA o endereço eletrônico. Pela ordem de prevalência vale o CNN: a
  falta do e-mail na qualificação não é defeito; a falta do documento de
  identificação (e da filiação, que o substitui) é. Na ata de usucapião o CNN
  art. 401, I, pede o endereço eletrônico expressamente — lá é defeito.
- **Ata de adjudicação compulsória.** O CN-MA art. 848, § 2º, diz que a ata
  «servirá como título hábil para ingresso no Registro de Imóveis»; o CNN art.
  440-G, § 2º, manda consignar que ela NÃO tem valor de título de propriedade
  e serve à instrução do pedido no registro (Lei 6.015/1973, art. 216-B). O
  LD07 consertou os outros dois elementos da ata (ônus e valor venal) e
  deixou este para o oficial. **Decidido em 21/10/2026 — 12 a (LH13):** segue
  o CNN, que prevalece; a minuta diz «a presente ata não tem valor de título
  de propriedade; presta-se à instrução do pedido de adjudicação compulsória
  perante o Registro de Imóveis e poderá ser aproveitada em processo
  judicial», e a frase do CN-MA saiu. ✓
- **Pública forma.** O CN-MA não tem artigo próprio; a matriz aplica, por
  analogia, as regras da autenticação (art. 836), da escritura (art. 798, I) e
  do selo (arts. 130 e 131).
- **Certidão em breve relato.** O CN-MA art. 851 define certidão como cópia
  «integral ou resumida». Desde o LD02 (21/10/2026) a casa a emite
  (`notas_certidao`, papel `NOTAS_CERTIDAO_BREVE_RELATO`) e ela **afirma só o
  que o livro registra em campo** — espécie, natureza, livro, folha, termo,
  data, partes com a qualidade, selo e margem —, sem resumir o teor: o objeto
  continua na de inteiro teor. Se o oficial quiser o objeto resumido, é ajuste
  do modelo (pergunta em `relatorios/LD02.perguntas.md`).
- **Ficha do cartão: quem verificou o preenchimento.** O CN-MA art. 864, § 1º,
  VI, pede o nome, a assinatura e o carimbo do tabelião ou preposto que
  verificou a ficha; a decisão do oficial de 31/08/2026 era que «o oficial não
  assina a ficha, só o cliente». **Decidido em 21/10/2026 — 9 b (LH13):** ao
  pé da ficha, «Preenchimento conferido por: NOME — função», com linha de
  assinatura e espaço para o carimbo, do escrevente que abriu o cartão (nome
  e função gravados na abertura). O cliente continua assinando só os
  autógrafos; o delegatário continua fora. ✓
- **Cônjuge e regime de bens na qualificação.** O CC art. 215, § 1º, III, os
  pede «quando necessário», e o CN-MA art. 798, V, quando o ato é sobre
  imóvel. Desde o LD07 a qualificação de quem é casado os traz quando a parte
  os tem, mas a falta dos dois NÃO se marca — `notas_teor.qualificar` não sabe
  se o ato é sobre imóvel, e exigir sempre seria escolher a leitura mais dura
  sem o oficial. Dito um dos dois, o outro sai marcado. A regra da trava é a
  pergunta 3 de `relatorios/LD07.perguntas.md`.

### O que o LD07 consertou (21/10/2026)

«corrija tudo» — o oficial, sobre os elementos que o LT02 achou faltando. 38
dos 40 casos `xfail` da matriz passaram, sem a marca:

- **Minutas** (24 casos): a escolha do INSS (declaração de não sujeição, ou a
  CND com número, data e local) e a do cadastro fiscal (Prefeitura, INCRA ou o
  comprovante de que não há lançamento) nas escrituras de imóvel; a ciência do
  negócio de risco na cessão de direitos hereditários; o ITBI na procuração em
  causa própria; a naturalidade na emancipação; na ata de usucapião o valor, o
  titular, a aquisição da posse, as circunscrições, o alerta da falsidade, o
  endereço eletrônico (e o cônjuge ou companheiro do requerente); na de
  adjudicação os ônus e o valor venal. As trocas estão declaradas no ouro do
  LF06D (`MINUTAS_MUDADAS_NO_LD07`).
- **Qualificação da pessoa física** (3): a parte do ato guarda o documento de
  identidade, a filiação, a união estável, o cônjuge e o regime de bens
  (`nt_ato_partes`); a tela do ato os pede; `qualificar` escolhe a frase e
  marca o documento e a união estável que faltam (o cônjuge, só se a metade
  foi dita — ver acima). A testemunha não é marcada.
- **Autenticação** (3): a ressalva do original (peça nova, campo na tela,
  coluna `nt_autenticacoes.ressalva`); a conferência da internet já existia
  (LD02) — a matriz passou a montá-la pelo montador do balcão.
- **Cartão de autógrafo** (3): «aberta em» com a data de abertura, a linha do
  título eleitoral (coluna `nt_cartoes.titulo_eleitor`, nas telas de abrir e
  corrigir) e cada forma de assinar três vezes.
- **Certidão positiva** (1): o termo (ou a ordem, no acervo) de cada ato.
- **Termo de presença** (1) e **pública forma** (3): já estavam no papel desde
  o LD02; a matriz passou a medir o que sai (a ordem, a moldura).

### Defeitos de MARCAÇÃO das minutas (o teor sai com marcador)

Achados ao preencher cada minuta por inteiro
(`test_a_minuta_preenchida_por_inteiro_nao_deixa_claro_nem_marcador`):
`ri_modelos_atos.preencher` resolve as cláusulas e as escolhas numa passada só,
e a expressão de cada uma não aceita outra dentro. **Os quatro foram
consertados no LD02 (21/10/2026)**, no texto da minuta (as trocas estão
declaradas no ouro do LF06D, `MINUTAS_MUDADAS_NO_LD02`); a trava da lavratura
continua valendo para a casa que personalizou a minuta antiga.

| Minuta | Defeito | Fonte | Situação |
|---|---|---|---|
| NT-ESC-USUFRUTO | a escolha `{ATO: …}` tinha `{DURAÇÃO: …}` dentro e ficava crua; havia duas escolhas «ATO» com opções diferentes respondendo pelo mesmo campo | CN-MA art. 795, § 2º | ✓ a duração foi para «SE INSTITUIÇÃO»; a frase do registro, para cada opção do ATO |
| NT-ESC-PARTILHA-ADJUDICACAO | duas escolhas «ATO» com opções diferentes, um campo só na tela | CN-MA art. 795, § 2º | ✓ a do destino dos bens é `{DESTINO DOS BENS: …}` |
| NT-ESC-DIRETIVAS-VONTADE | a cláusula «SE NOMEAR PROCURADOR DE SAÚDE: …» tinha outra «SE» dentro; não virava caixa na tela | CN-MA art. 795, § 2º | ✓ as duas cláusulas são vizinhas |
| NT-TESTAMENTO-CERRADO | «[ÚLTIMAS PALAVRAS DO TESTADOR]» entre aspas «» era lido como cláusula opcional | CC art. 1.869 | ✓ entre aspas curvas (“ ”) |

### Escrituras

#### Escritura de compra e venda de imóvel urbano

minuta `modelos_padrao/notas/minutas/NT-ESC-COMPRA-VENDA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| natureza do negócio e o objeto | CN-MA art. 798, VIII | ✓ |
| características, confrontações e localização do imóvel | Lei 6.015/1973, art. 225; CN-MA art. 800, I | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| preço e forma de pagamento | CN-MA art. 798, VIII e IX | ✓ |
| imposto de transmissão certificado (guia, data e valor quando houver) | CN-MA arts. 791, VIII, e 798, § 3º | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ |
| número predial e rua, se edificado | CN-MA art. 800, V | ✓ |
| referência à emissão da DOI | CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º) | ✓ |
| certidão atualizada da matrícula e de ônus reais | CN-MA art. 791, IV (Lei 7.433/1985, art. 1º, § 2º — conferir no texto oficial) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de compra e venda de imóvel rural

minuta `modelos_padrao/notas/minutas/NT-ESC-COMPRA-VENDA-RURAL.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| natureza do negócio e o objeto | CN-MA art. 798, VIII | ✓ |
| características, confrontações e localização do imóvel | Lei 6.015/1973, art. 225; CN-MA art. 800, I | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| preço e forma de pagamento | CN-MA art. 798, VIII e IX | ✓ |
| imposto de transmissão certificado (guia, data e valor quando houver) | CN-MA arts. 791, VIII, e 798, § 3º | ✓ |
| CCIR: código do imóvel, nome e nacionalidade do detentor, denominação | CN-MA arts. 801, V, e 802, § 5º | ✓ |
| módulo e área do imóvel rural | CN-MA art. 801, V | ✓ |
| ITR dos cinco últimos exercícios | CN-MA arts. 791, XI, e 802 | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ |
| referência à emissão da DOI | CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de doação

minuta `modelos_padrao/notas/minutas/NT-ESC-DOACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| natureza do negócio e o objeto | CN-MA art. 798, VIII | ✓ |
| aceitação do donatário | CC art. 539 (conferir no texto oficial) | ✓ |
| características, confrontações e localização do imóvel | Lei 6.015/1973, art. 225; CN-MA art. 800, I | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| imposto de transmissão certificado (guia, data e valor quando houver) | CN-MA arts. 791, VIII, e 798, § 3º | ✓ |
| referência à emissão da DOI | CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º) | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de hipoteca

minuta `modelos_padrao/notas/minutas/NT-ESC-HIPOTECA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| o valor da dívida, o prazo e os juros | CC art. 1.424, I a III (conferir no texto oficial) | ✓ |
| o bem dado em garantia, especificado | CC art. 1.424, IV; Lei 6.015/1973, art. 225 | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| a outorga do cônjuge do devedor | CC art. 1.647, I (conferir no texto oficial) | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de alienação fiduciária de imóvel

minuta `modelos_padrao/notas/minutas/NT-ESC-ALIENACAO-FIDUCIARIA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| o principal da dívida, o prazo, os juros e os encargos | Lei 9.514/1997, art. 24, I a III (conferir no texto oficial) | ✓ |
| a propriedade fiduciária, com a descrição do imóvel | Lei 9.514/1997, art. 24, IV (conferir no texto oficial) | ✓ |
| a livre utilização do imóvel pelo fiduciante | Lei 9.514/1997, art. 24, V (conferir no texto oficial) | ✓ |
| o valor do imóvel para leilão e o critério de revisão | Lei 9.514/1997, art. 24, VI (conferir no texto oficial) | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de confissão de dívida e dação em pagamento

minuta `modelos_padrao/notas/minutas/NT-ESC-CONFISSAO-DACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| a dívida confessada | CC art. 356 (conferir no texto oficial) | ✓ |
| o imóvel dado em pagamento e o valor atribuído | CC art. 357; CN-MA art. 800, I | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| imposto de transmissão certificado (guia, data e valor quando houver) | CN-MA arts. 791, VIII, e 798, § 3º | ✓ |
| referência à emissão da DOI | CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º) | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de permuta

minuta `modelos_padrao/notas/minutas/NT-ESC-PERMUTA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| os dois imóveis permutados, descritos, e o valor de cada um | CC art. 533; Lei 6.015/1973, art. 225 | ✓ |
| a torna, quando houver | CC art. 533 (conferir no texto oficial) | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| imposto de transmissão certificado (guia, data e valor quando houver) | CN-MA arts. 791, VIII, e 798, § 3º | ✓ |
| referência à emissão da DOI | CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º) | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de usufruto

minuta `modelos_padrao/notas/minutas/NT-ESC-USUFRUTO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| o usufruto, o imóvel e o prazo | CC arts. 1.390 e 1.410 (conferir no texto oficial) | ✓ |
| referência à matrícula ou ao registro anterior, com o número e o cartório | Lei 6.015/1973, art. 222 | ✓ |
| imposto de transmissão certificado (guia, data e valor quando houver) | CN-MA arts. 791, VIII, e 798, § 3º | ✓ |
| certidão do INSS (número, data e local) ou a declaração de que as partes não estão sujeitas | CN-MA art. 800, III (Lei 8.212/1991, art. 47) | ✓ consertado no LD07 (21/10/2026) |
| número do cadastro fiscal do imóvel (Prefeitura ou INCRA) | CN-MA art. 800, IV | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de cessão de direitos hereditários

minuta `modelos_padrao/notas/minutas/NT-ESC-CESSAO-HEREDITARIA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| as testemunhas do ato, qualificadas | CC arts. 1.864, II, e 1.868, I; CN-MA art. 799, VIII | ✓ |
| o autor da herança e o registro do óbito | CN-MA art. 803 (identificação da herança) | ✓ |
| a cessão abrange também as dívidas do espólio | CN-MA art. 803 | ✓ |
| a ciência dos demais coerdeiros | CN-MA art. 804 (CC art. 1.795) | ✓ |
| o imposto de transmissão | CN-MA art. 804 | ✓ |
| a outorga do cônjuge do cedente, ou o regime que a dispensa | CN-MA art. 804, §§ 4º e 5º | ✓ |
| o quinhão em fração, e não em dinheiro | CN-MA art. 805, parágrafo único | ✓ |
| a ciência de que é negócio de risco: só produz efeito na partilha, se o bem couber ao cedente | CN-MA art. 804, § 8º | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de inventário e partilha

minuta `modelos_padrao/notas/minutas/NT-ESC-INVENTARIO-PARTILHA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| autor da herança e o registro do óbito (dia, lugar, livro, folha, termo e serventia) | CN-MA art. 812, § 2º (Res. CNJ 35/2007, art. 21) | ✓ |
| a qualificação completa do autor da herança e o regime de bens | CN-MA art. 812, § 2º | ✓ |
| a data de expedição da certidão de óbito | CN-MA art. 812, § 2º | ✓ |
| a declaração de que não há testamento nem outros herdeiros | CN-MA arts. 811, X, e 812, § 2º | ✓ |
| a certidão da CENSEC (RCTO) sobre a inexistência de testamento | CN-MA arts. 811, XI, e 818, V; CNN art. 441, II | ✓ |
| os herdeiros, com o vínculo de parentesco | CN-MA art. 812, VI | ✓ |
| o inventariante | CN-MA arts. 811, XV, e 812, VII | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| os bens, com os valores, e a partilha | CN-MA art. 812, IX, X e XIV | ✓ |
| os impostos pagos, especificados | CN-MA arts. 808, § 2º, e 812, XVII | ✓ |
| as certidões negativas das Fazendas Federal, Estadual e Municipal | CN-MA arts. 808, § 3º, e 817, parágrafo único | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de sobrepartilha

minuta `modelos_padrao/notas/minutas/NT-ESC-SOBREPARTILHA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| autor da herança e o registro do óbito (dia, lugar, livro, folha, termo e serventia) | CN-MA art. 812, § 2º (Res. CNJ 35/2007, art. 21) | ✓ |
| o inventário anterior (processo ou escritura) | CN-MA art. 813 | ✓ |
| os bens sobrepartilháveis, com valores, e a sobrepartilha | CN-MA art. 817 | ✓ |
| os herdeiros | CN-MA art. 812, VI | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| o imposto | CN-MA art. 817 | ✓ |
| as certidões negativas das Fazendas Federal, Estadual e Municipal | CN-MA arts. 808, § 3º, e 817, parágrafo único | ✓ |
| a certidão da CENSEC (RCTO) sobre a inexistência de testamento | CN-MA arts. 811, XI, e 818, V; CNN art. 441, II | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de partilha ou adjudicação

minuta `modelos_padrao/notas/minutas/NT-ESC-PARTILHA-ADJUDICACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| autor da herança e o registro do óbito (dia, lugar, livro, folha, termo e serventia) | CN-MA art. 812, § 2º (Res. CNJ 35/2007, art. 21) | ✓ |
| os herdeiros, ou o herdeiro único | CN-MA art. 814 | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| os bens com o valor da avaliação, e a partilha | CN-MA arts. 817 e 819, parágrafo único | ✓ |
| o imposto | CN-MA arts. 817 e 819, parágrafo único | ✓ |
| as certidões negativas das Fazendas Federal, Estadual e Municipal | CN-MA arts. 808, § 3º, e 817, parágrafo único | ✓ |
| a certidão da CENSEC sobre testamento | CN-MA art. 818, V | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de nomeação de inventariante

minuta `modelos_padrao/notas/minutas/NT-ESC-NOMEACAO-INVENTARIANTE.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| autor da herança e o registro do óbito (dia, lugar, livro, folha, termo e serventia) | CN-MA art. 812, § 2º (Res. CNJ 35/2007, art. 21) | ✓ |
| o inventariante nomeado | CN-MA art. 810 | ✓ |
| os poderes perante bancos e repartições fiscais | CN-MA art. 810 | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de divórcio consensual

minuta `modelos_padrao/notas/minutas/NT-ESC-DIVORCIO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o casamento: data, regime de bens e o registro (livro, folha, termo, serventia) | CN-MA arts. 812, § 1º, 824, III, e 826, I | ✓ |
| a descrição e a partilha dos bens comuns | CN-MA art. 822 | ✓ |
| a pensão alimentícia entre os cônjuges | CN-MA art. 822 | ✓ |
| o nome que o cônjuge passa a usar | CN-MA art. 822 e § 14 | ✓ |
| os filhos incapazes: compromisso de levar ao Judiciário | CN-MA art. 822, § 1º | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| o processo judicial anterior, se houver | CN-MA art. 821 (por analogia) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de separação consensual

minuta `modelos_padrao/notas/minutas/NT-ESC-SEPARACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| a vontade de não manter a sociedade conjugal | CN-MA art. 823, I | ✓ |
| o casamento: data, regime de bens e o registro (livro, folha, termo, serventia) | CN-MA arts. 812, § 1º, 824, III, e 826, I | ✓ |
| a partilha, a pensão e o nome | CN-MA art. 822 | ✓ |
| a ausência de filhos incapazes, ou o compromisso | CN-MA arts. 822, § 1º, e 823, II | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de conversão da separação em divórcio

minuta `modelos_padrao/notas/minutas/NT-ESC-CONVERSAO-DIVORCIO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| a separação anterior e a sua averbação | CN-MA art. 830 | ✓ |
| o casamento: data, regime e registro | CN-MA art. 830 | ✓ |
| a partilha, a pensão e o nome | CN-MA art. 822 | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de restabelecimento da sociedade conjugal

minuta `modelos_padrao/notas/minutas/NT-ESC-RESTABELECIMENTO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o casamento e a separação que se desfaz | CN-MA arts. 828 e 829 | ✓ |
| a orientação de levar o traslado ao registro civil | CN-MA art. 829, I | ✓ |
| a anotação à margem da separação, ou a comunicação | CN-MA art. 829, II e III | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura declaratória de união estável

minuta `modelos_padrao/notas/minutas/NT-ESC-UNIAO-ESTAVEL.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| a data de início da união | CNN art. 537, § 4º; CC art. 1.723 | ✓ |
| o regime de bens | CC art. 1.725 (conferir no texto oficial) | ✓ |
| a separação de fato de quem ainda é casado | CC art. 1.723, § 1º (conferir no texto oficial) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de dissolução de união estável

minuta `modelos_padrao/notas/minutas/NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o início e o fim da união | CNN art. 537, § 4º; CN-MA art. 822 | ✓ |
| o regime de bens da união | CN-MA art. 822 | ✓ |
| a partilha, a pensão e o nome | CN-MA art. 822 | ✓ |
| advogado das partes, qualificado e com a inscrição na OAB | CN-MA arts. 808, § 1º, 819 e 822, § 5º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de emancipação

minuta `modelos_padrao/notas/minutas/NT-ESC-EMANCIPACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| a concessão da emancipação pelos pais | CC art. 5º, parágrafo único, I (conferir no texto oficial) | ✓ |
| a data de nascimento e o registro do nascimento do emancipado (data e cartório) | Lei 6.015/1973, art. 90, 2º | ✓ |
| a filiação do emancipado | Lei 6.015/1973, art. 90, 2º | ✓ |
| a naturalidade do emancipado e dos pais | Lei 6.015/1973, art. 90, 2º e 3º | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de pacto antenupcial

minuta `modelos_padrao/notas/minutas/NT-ESC-PACTO-ANTENUPCIAL.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o regime de bens escolhido | CC art. 1.653 (conferir no texto oficial) | ✓ |
| a habilitação para o casamento | CC art. 1.653 | ✓ |
| o registro no Registro de Imóveis do domicílio | CC art. 1.657; Lei 6.015/1973, art. 244 (conferir no texto oficial) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de quitação

minuta `modelos_padrao/notas/minutas/NT-ESC-QUITACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o valor e a espécie da dívida quitada | CC art. 320 (conferir no texto oficial) | ✓ |
| o nome do devedor | CC art. 320 | ✓ |
| o tempo e o lugar do pagamento | CC art. 320 | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de distrato

minuta `modelos_padrao/notas/minutas/NT-ESC-DISTRATO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o contrato desfeito, identificado (natureza, data, livro, folhas, serventia) | CC art. 472 (conferir no texto oficial) | ✓ |
| o objeto e as restituições | CC art. 472 | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Escritura de diretivas antecipadas de vontade

minuta `modelos_padrao/notas/minutas/NT-ESC-DIRETIVAS-VONTADE.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| a capacidade do declarante | CN-MA art. 876 | ✓ |
| as diretrizes sobre cuidados e tratamentos de saúde | CN-MA art. 876 | ✓ |
| o procurador de saúde, quando nomeado | CN-MA art. 877 | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

### Procurações e mandato

#### Procuração pública

minuta `modelos_padrao/notas/minutas/NT-PROC-PUBLICA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| os poderes, com a designação e a extensão | CC art. 654, § 1º (conferir no texto oficial) | ✓ |
| os poderes especiais, expressos | CC art. 661, § 1º (conferir no texto oficial) | ✓ |
| o imóvel e a certidão atualizada do registro de imóveis | CN-MA art. 833 | ✓ |
| o prazo do mandato | CC art. 682, IV (conferir no texto oficial) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Procuração em causa própria

minuta `modelos_padrao/notas/minutas/NT-PROC-CAUSA-PROPRIA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| o objeto, com os poderes que exorbitam a administração | CN-MA art. 835, IV | ✓ |
| o preço pago | CN-MA art. 835, II | ✓ |
| a irrevogabilidade | CC art. 685 (conferir no texto oficial) | ✓ |
| o prévio recolhimento do ITBI | CN-MA art. 835, III | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Procuração para fins previdenciários

minuta `modelos_padrao/notas/minutas/NT-PROC-PREVIDENCIARIA.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| a finalidade junto ao INSS e o benefício | Lei 8.213/1991, art. 109 (conferir no texto oficial) | ✓ |
| a validade não superior a doze meses | Lei 8.213/1991, art. 109 (conferir no texto oficial) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Substabelecimento

minuta `modelos_padrao/notas/minutas/NT-SUBSTABELECIMENTO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| o mandato de origem: serventia, data, livro e folhas | CN-MA arts. 789, § 1º, e 831 | ✓ |
| com ou sem reserva de poderes | CC art. 667 (conferir no texto oficial) | ✓ |
| os poderes substabelecidos | CN-MA art. 789 | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Revogação de mandato

minuta `modelos_padrao/notas/minutas/NT-REVOGACAO-MANDATO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| nome e qualificação da outra parte (outorgado) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ |
| o mandato de origem: serventia, data, livro e folhas | CN-MA arts. 789, § 1º, e 831 | ✓ |
| a advertência de que é imprescindível notificar o mandatário | CN-MA art. 831, § 2º | ✓ |
| a anotação à margem do ato revogado, ou a comunicação à outra serventia | CN-MA art. 831 e § 1º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Renúncia de mandato

minuta `modelos_padrao/notas/minutas/NT-RENUNCIA-MANDATO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o mandante | CN-MA art. 831, § 4º | ✓ |
| o mandato de origem: serventia, data, livro e folhas | CN-MA arts. 789, § 1º, e 831 | ✓ |
| a advertência de comunicar a renúncia ao mandante | CN-MA art. 831, § 4º (CC art. 688) | ✓ |
| a anotação à margem, ou a comunicação à outra serventia | CN-MA art. 831 e § 1º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

### Testamentos

#### Testamento público

minuta `modelos_padrao/notas/minutas/NT-TESTAMENTO-PUBLICO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| hora do ato | CN-MA art. 847, § 1º, I (ata); CC art. 1.864 (praxe do testamento) | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| as testemunhas do ato, qualificadas | CC arts. 1.864, II, e 1.868, I; CN-MA art. 799, VIII | ✓ |
| a capacidade do testador | CC art. 1.860 (conferir no texto oficial) | ✓ |
| escrito pelo tabelião, de acordo com as declarações do testador | CC art. 1.864, I (conferir no texto oficial) | ✓ |
| lido em voz alta ao testador e às duas testemunhas, a um só tempo | CC art. 1.864, II | ✓ |
| assinado pelo testador, pelas testemunhas e pelo tabelião | CC art. 1.864, III | ✓ |
| as disposições, com cada herdeiro ou legatário | CC art. 1.857 (conferir no texto oficial) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Testamento cerrado — auto de aprovação

minuta `modelos_padrao/notas/minutas/NT-TESTAMENTO-CERRADO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| hora do ato | CN-MA art. 847, § 1º, I (ata); CC art. 1.864 (praxe do testamento) | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| as testemunhas do ato, qualificadas | CC arts. 1.864, II, e 1.868, I; CN-MA art. 799, VIII | ✓ |
| a entrega do testamento ao tabelião, na presença de duas testemunhas | CC art. 1.868, I (conferir no texto oficial) | ✓ |
| a declaração de que é o seu testamento e quer que seja aprovado | CC art. 1.868, II | ✓ |
| o auto começa logo depois da última palavra do testador | CC art. 1.869 | ✓ |
| o auto lido ao testador e às testemunhas, e assinado por todos | CC art. 1.868, III e IV | ✓ |
| o testamento cerrado e cosido | CC art. 1.869 | ✓ |
| a nota no livro do lugar, dia, mês e ano da aprovação | CC art. 1.874 | ✓ |
| o número de folhas do testamento | CC art. 1.868 (praxe) | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

### Atas notariais

#### Ata notarial

minuta `modelos_padrao/notas/minutas/NT-ATA-NOTARIAL.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| hora do ato | CN-MA art. 847, § 1º, I (ata); CC art. 1.864 (praxe do testamento) | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| as testemunhas do ato, qualificadas | CC arts. 1.864, II, e 1.868, I; CN-MA art. 799, VIII | ✓ |
| o solicitante, nome e qualificação | CN-MA art. 847, § 1º, II | ✓ |
| a narração circunstanciada dos fatos | CN-MA art. 847, § 1º, III | ✓ |
| o documento transcrito na íntegra, quando houver | CN-MA art. 847, § 4º | ✓ |
| os anexos numerados e arquivados | CN-MA art. 847, § 5º | ✓ |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Ata notarial para usucapião extrajudicial

minuta `modelos_padrao/notas/minutas/NT-ATA-USUCAPIAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| hora do ato | CN-MA art. 847, § 1º, I (ata); CC art. 1.864 (praxe do testamento) | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| as testemunhas do ato, qualificadas | CC arts. 1.864, II, e 1.868, I; CN-MA art. 799, VIII | ✓ |
| a modalidade de usucapião e a base legal | CNN art. 401, I, d | ✓ |
| a descrição do imóvel e as características | CNN art. 401, I, a | ✓ |
| a matrícula, ou a informação de que não há | CNN art. 400, IV | ✓ |
| o tempo e as características da posse do requerente e dos antecessores | CNN art. 401, I, b; CN-MA art. 846, V | ✓ |
| os documentos da origem, continuidade e tempo da posse | CNN art. 401, III | ✓ |
| a ata não declara a propriedade: serve ao pedido no registro de imóveis | CNN art. 402, § 3º | ✓ |
| o valor do imóvel | CNN arts. 400, V, e 401, I, f | ✓ consertado no LD07 (21/10/2026) |
| o titular do imóvel na matrícula | CNN art. 401, I | ✓ consertado no LD07 (21/10/2026) |
| a forma de aquisição da posse pelo requerente | CNN art. 401, I, c | ✓ consertado no LD07 (21/10/2026) |
| o número de imóveis e as circunscrições em que estão | CNN art. 401, I, e | ✓ consertado no LD07 (21/10/2026) |
| o alerta ao requerente e às testemunhas de que declaração falsa é crime | CNN art. 402 | ✓ consertado no LD07 (21/10/2026) |
| o endereço eletrônico do requerente | CNN art. 401, I | ✓ consertado no LD07 (21/10/2026) |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

#### Ata notarial para adjudicação compulsória

minuta `modelos_padrao/notas/minutas/NT-ATA-ADJUDICACAO.txt`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| data do ato, com dia, mês e ano, por extenso e em algarismos | CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I | ✓ |
| hora do ato | CN-MA art. 847, § 1º, I (ata); CC art. 1.864 (praxe do testamento) | ✓ |
| local do ato (cidade e estado) | CC art. 215, § 1º, I; CN-MA art. 798, I | ✓ |
| quem lavra o ato, com o cargo | CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica) | ✓ |
| reconhecimento da identidade de quem comparece | CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III | ✓ |
| nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF) | CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111 | ✓ |
| o requerente e a sua qualidade (promitente comprador ou cessionário) | CN-MA art. 848, § 1º, I | ✓ |
| o imóvel conforme a matrícula e o cadastro imobiliário | CN-MA art. 848, § 1º, II; CNN art. 440-G, I | ✓ |
| o contrato e a prova da quitação | CN-MA art. 848, § 1º, III; CNN art. 440-G, II e III | ✓ |
| a notificação do promitente vendedor e a sua inércia | CN-MA art. 848, § 1º, IV; CNN art. 440-G, IV | ✓ |
| a certidão de inexistência de litígio | CN-MA art. 848, § 1º, V | ✓ |
| os ônus e gravames do imóvel | CNN art. 440-G, I | ✓ consertado no LD07 (21/10/2026) |
| o valor venal do imóvel | CNN art. 440-G, V | ✓ consertado no LD07 (21/10/2026) |
| a advertência de que a ata não é título de propriedade | CNN art. 440-G, § 2º (no lugar do CN-MA art. 848, § 2º, que dizia o contrário) | ✓ consertado no LH13 (21/10/2026) — resposta do oficial à pergunta 12: letra a |
| declaração de que o ato foi lido | CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV | ✓ |
| encerramento do ato | CN-MA art. 798, XII | ✓ |
| assinatura das partes e de quem lavra | CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V | ✓ |

### Papéis do catálogo (balcão, termo, traslado, certidões)

#### Qualificação da pessoa física (todo ato de livro)

papel `NOTAS_QUALIFICACAO_PF` e as peças dele, montados por `notas_teor.qualificar` (desde o LD07)

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o nome completo | CC art. 215, § 1º, III; CNN art. 111 | ✓ |
| a nacionalidade | CC art. 215, § 1º, III; CNN art. 111 | ✓ |
| o estado civil | CC art. 215, § 1º, III; CNN art. 111 | ✓ |
| a profissão | CC art. 215, § 1º, III; CNN art. 111 | ✓ |
| o CPF | CNN art. 111; CN-MA art. 798, V e § 1º | ✓ |
| o domicílio e a residência | CC art. 215, § 1º, III; CNN art. 111 | ✓ |
| o documento de identificação (ou, na falta dele, a filiação) | CNN art. 111; CN-MA art. 798, V | ✓ consertado no LD07 (21/10/2026) |
| a existência de união estável | CNN art. 111 | ✓ consertado no LD07 (21/10/2026) |
| o nome do cônjuge e o regime de bens, quando casado (ato sobre imóvel) | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ consertado no LD07 (21/10/2026) |

#### Qualificação da pessoa jurídica

papel `NOTAS_QUALIFICACAO_PJ`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o nome empresarial | CN-MA art. 791, II | ✓ |
| o CNPJ | CN-MA art. 798, § 1º | ✓ |
| a sede | CC art. 215, § 1º, III | ✓ |

#### Reconhecimento de firma por semelhança

papel `NOTAS_RECONHECIMENTO_SEMELHANCA`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a espécie do reconhecimento, expressa | CN-MA art. 861, §§ 2º e 5º | ✓ |
| o nome de quem teve a firma reconhecida, sem «supra» ou «retro» | CN-MA art. 861, § 5º | ✓ |

#### Reconhecimento de firma por autenticidade

papel `NOTAS_RECONHECIMENTO_AUTENTICIDADE`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a espécie do reconhecimento, expressa | CN-MA art. 861, §§ 1º e 5º | ✓ |
| o nome de quem teve a firma reconhecida | CN-MA art. 861, § 5º | ✓ |

#### Reconhecimento de sinal público

papel `NOTAS_RECONHECIMENTO_SINAL`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o reconhecimento do sinal público | CN-MA arts. 870 e 873 | ✓ |
| o nome de quem tem o sinal | CN-MA art. 873 | ✓ |

#### Fecho da etiqueta: local e data

papel `NOTAS_ETIQUETA_FECHO__local_e_data`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o local e a data do ato | CN-MA art. 861, § 1º (data do reconhecimento) | ✓ |

#### Etiqueta do reconhecimento e da autenticação (templates/notas_etiqueta.html)

`templates/notas_etiqueta.html`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o nome de quem pratica o ato, legível | CN-MA art. 861, § 10 | ✓ |
| a função de quem pratica | CN-MA art. 861, § 10 | ✓ |
| o selo no corpo do ato | CN-MA arts. 130 e 131 | ✓ |
| o QR do selo, para a consulta pública | CN-MA art. 132 | ✓ |
| os emolumentos que o selo declara | CN-MA art. 87, XVI | ✓ |

#### Termo de comparecimento (presença) do reconhecimento por autenticidade

papel `NOTAS_TERMO_COMPARECIMENTO`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o nome de quem compareceu | CN-MA art. 866 | ✓ |
| o documento de identificação | CN-MA art. 866 | ✓ |
| o número do selo do reconhecimento | CN-MA art. 866 | ✓ |
| a data do comparecimento | CN-MA art. 866 | ✓ |
| a assinatura do interessado | CN-MA art. 866 | ✓ |
| a ordem (o número) do termo | CN-MA art. 866 | ✓ o claro é do LD02; a matriz passou a montá-lo no LD07 |

#### Autenticação de cópia

papel `NOTAS_AUTENTICACAO` e a peça `__ressalva`, montados por `notas_schema.texto_autenticacao` (desde o LD07)

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a conferência da cópia com o original | CN-MA art. 836 | ✓ |
| a ressalva da rasura ou do defeito do original | CN-MA art. 836 | ✓ consertado no LD07 (21/10/2026) |

#### Autenticação de documento da internet

papel `NOTAS_AUTENTICACAO_INTERNET` e a peça `__conferencia`, montados por `notas_schema.texto_autenticacao` (desde o LD07)

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a conferência com o original | CN-MA art. 839 | ✓ |
| o endereço eletrônico de acesso | CN-MA art. 839, § 1º | ✓ a peça da conferência é do LD02; a matriz passou a montá-la no LD07 |
| o horário da conferência | CN-MA art. 839, § 1º | ✓ a peça do LD02 diz «às 10:30 horas» desde o LD07 |

#### Cartão de autógrafo (ficha de firma)

papel `NOTAS_CARTAO_FICHA`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a numeração crescente da ficha | CN-MA art. 864, § 1º, I | ✓ |
| o nome, o endereço, a profissão, o estado civil e o nascimento | CN-MA art. 864, § 1º, III | ✓ |
| o CPF e o documento de identidade | CN-MA art. 864, § 1º, IV | ✓ |
| o selo de abertura de firma | CN-MA art. 864, caput | ✓ |
| a data de abertura | CN-MA art. 864, § 1º, I | ✓ consertado no LD07 (21/10/2026) |
| o título eleitoral, se houver | CN-MA art. 864, § 1º, III | ✓ consertado no LD07 (21/10/2026) |
| a data de emissão do documento de identidade | CN-MA art. 864, § 1º, IV | ✓ (LD02) |
| a firma colocada ao menos três vezes | CN-MA arts. 864, § 1º, V, e 867 | ✓ consertado no LD07 (21/10/2026) |
| nome, assinatura e carimbo de quem conferiu o preenchimento | CN-MA art. 864, § 1º, VI | ✓ consertado no LH13 (21/10/2026) — resposta do oficial à pergunta 9: letra b (o escrevente que abriu o cartão) |

#### Pública forma

papel `NOTAS_PUBLICA_FORMA` (o teor congelado) e a moldura `nt_publica_forma.papel_html` (desde o LD07)

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| o número | CN-MA art. 130 (controle do ato) | ✓ |
| o apresentante | CN-MA art. 791, I | ✓ |
| o documento original identificado | CN-MA art. 836 (por analogia) | ✓ |
| a transcrição na íntegra | CN-MA arts. 794 e 795 | ✓ |
| a ressalva, ou a declaração de que o original não tem rasura | CN-MA art. 836 | ✓ |
| a conferência com o original | CN-MA art. 836 | ✓ |
| o local e a data | CN-MA art. 798, I (por analogia) | ✓ na moldura do papel (LD02), `nt_publica_forma.papel_html` desde o LD07 |
| quem a expede, com o nome | CN-MA art. 861, § 10 (por analogia) | ✓ na moldura do papel (LD02), `nt_publica_forma.papel_html` desde o LD07 |
| o selo e os emolumentos no corpo do papel | CN-MA arts. 87, XVI, 130 e 131 | ✓ o carimbo no lugar de `@@SELO@@` da moldura (LD02), desde o LD07 em `papel_html` |

#### Termo do livro (o ato como vai ao livro)

papel `NOTAS_TERMO_LIVRO`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a serventia (nome e CNS) | CN-MA art. 180 (identificação da serventia) | ✓ |
| o livro, a folha e o termo | CN-MA arts. 792 e 851, § 1º | ✓ |
| o título do instrumento | CN-MA art. 798, VIII | ✓ |
| o teor do ato | CN-MA art. 798 | ✓ |
| o selo (número, QR e emolumentos) no corpo do ato | CN-MA arts. 87, XVI, 130 e 131 | ✓ |
| as linhas de assinatura das partes e de quem lavra | CN-MA art. 798, XIII | ✓ |

#### Traslado

papel `NOTAS_TRASLADO`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| a serventia (nome e CNS) | CN-MA art. 180 | ✓ |
| os números do livro e das folhas | CN-MA art. 850, § 2º | ✓ |
| o inteiro teor do ato | CN-MA art. 850 e § 2º | ✓ |
| a menção «traslado» | CN-MA art. 850, § 2º | ✓ |
| as assinaturas | CN-MA art. 850, § 2º | ✓ |
| o selo no corpo do papel | CN-MA arts. 130 e 131 | ✓ |
| as anotações à margem | CN-MA art. 831; CC art. 217 | ✓ |
| o local e a data | CN-MA art. 850 (com a mesma data) | ✓ |

#### Certidão de inteiro teor

papel `NOTAS_CERTIDAO_INTEIRO_TEOR`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| quem a requer | CN-MA art. 851, § 3º | ✓ |
| a localização precisa: livro, folha e termo | CN-MA art. 851, § 1º | ✓ |
| a espécie do ato e a data em que foi lavrado | CN-MA art. 851, § 1º | ✓ |
| o teor na íntegra | CN-MA art. 851; CC art. 217 | ✓ |
| o selo do ato, com o que ele declara | CN-MA arts. 87, XVI, 131 e 851 | ✓ |
| as anotações à margem | CN-MA arts. 831 e 851; CC art. 217 | ✓ |
| a fé de quem certifica | CN-MA art. 849 | ✓ |

#### Certidão positiva (por busca)

papel `NOTAS_CERTIDAO_POSITIVA`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| quem a requer | CN-MA art. 851, § 3º | ✓ |
| quem se buscou e o período | CN-MA art. 851 | ✓ |
| cada ato achado: espécie, natureza, livro, folha, data e qualidade | CN-MA art. 851, § 1º | ✓ |
| o número (termo) de cada ato achado | CN-MA arts. 792 e 851, § 1º | ✓ consertado no LD07 (21/10/2026) |
| a fé de quem certifica | CN-MA art. 849 | ✓ |

#### Certidão negativa (por busca)

papel `NOTAS_CERTIDAO_NEGATIVA`

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| quem a requer | CN-MA art. 851, § 3º | ✓ |
| quem se buscou e o período | CN-MA art. 851 | ✓ |
| o resultado: nada consta | CN-MA art. 851 | ✓ |
| a fé de quem certifica | CN-MA art. 849 | ✓ |

#### Certidão em breve relato (do ato identificado)

papel `NOTAS_CERTIDAO_BREVE_RELATO` — LD02, 21/10/2026

| Elemento obrigatório | Fonte | No modelo |
|---|---|---|
| quem a requer | CN-MA art. 851, § 3º | ✓ |
| a localização precisa: livro, folha e termo | CN-MA art. 851, § 1º | ✓ |
| a espécie e a natureza do ato, e a data em que foi lavrado | CN-MA art. 851, § 1º | ✓ |
| a forma: breve relato | CN-MA art. 851 («cópia integral ou resumida») | ✓ |
| as partes e a qualidade em que figuram no ato | CN-MA art. 851, § 1º | ✓ |
| o selo do ato, com o que ele declara | CN-MA arts. 87, XVI, 131 e 851 | ✓ |
| as anotações à margem | CN-MA arts. 831 e 851; CC art. 217 | ✓ |
| a fé de quem certifica | CN-MA art. 849 | ✓ |

## Registro de Imóveis — LT03 (20/10/2026)

**Fontes, na ordem de prevalência:** Lei 6.015/1973 (**LRP**, texto compilado do
Planalto baixado em 20/10/2026 em `migracao-pg/referencia/normas/lei_6015_compilada.txt`);
Lei 8.935/1994; o Código Nacional de Normas do Foro Extrajudicial (Prov. CNJ
149/2023 e alterações, **CNN**, versão atualizada do CNJ em
`referencia/normas/cnn_prov_149_2023.txt`); e o Código de Normas Extrajudicial
do MA (Prov. COGEX 28/2026, **CN-MA**, em `referencia/codigo_de_normas_extrajudicial_ma.txt`).

**Como ler.** Cada tabela é um papel do RI (o TERMO que vai ao livro ou a
CERTIDÃO que vai para fora), e cada linha é um elemento que a lei ou a norma
exige, com o artigo. A mesma matriz é o parâmetro de
`tests/test_requisitos_ri.py`, que confere três coisas para cada linha: o
padrão da casa (`modelos_padrao/ri/`) tem o campo; o papel montado com um
contexto de ensaio completo diz o rótulo e o valor; e esta página traz o
elemento e o artigo. Os fluxos inteiros, pelas telas, estão em
`tests/test_fluxo_ri.py` (ver `docs/COBERTURA_FLUXOS.md`).

**Situação:** ✓ o modelo tem e o papel diz; ⚠ DEFEITO — o modelo não tem (o
teste está `xfail(strict=True)` com o artigo, e a nota diz por que não se
consertou aqui).

### Prenotação — comprovante do Livro 1

Modelo da casa: `RI_PRENOTACAO`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| número de ordem | LRP art. 175, I; art. 183 | ✓ |
| livro de protocolo | LRP art. 173, I | ✓ |
| data da apresentação | LRP art. 175, II; art. 183 | ✓ |
| hora da apresentação | LRP art. 182; CN-MA art. 447 | ✓ |
| apresentante | LRP art. 175, III; CN-MA art. 444, IV | ✓ |
| natureza formal do título | LRP art. 175, IV; CN-MA art. 444, V | ✓ |
| ato que o título formaliza (objeto) | LRP art. 175, V | ✓ |
| prazo da prenotação | LRP art. 205; CN-MA arts. 436 e 452 | ✓ |
| a serventia que recebe | CN-MA art. 443, § 2º | ✓ |
| quem emitiu, com a função | Lei 8.935/1994, arts. 20 e 21 | ✓ |

### Matrícula — termo de abertura (Livro 2)

Modelo da casa: `RI_FICHA`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| data da abertura | LRP art. 176, § 1º, II, 2 | ✓ |
| logradouro e número | LRP art. 176, § 1º, II, 3, b | ✓ |
| localização | LRP art. 176, § 1º, II, 3 | ✓ |
| área | LRP art. 176, § 1º, II, 3 | ✓ |
| confrontações | LRP art. 176, § 1º, II, 3 | ✓ consertado no LT03 — a tela «Nova matrícula» não tinha o campo; passou a ter |
| designação cadastral (inscrição municipal) | LRP art. 176, § 1º, II, 3, b | ✓ consertado no LT03 — o modelo não imprimia e a tela não pedia; os dois passaram a ter |
| imóvel rural: código do imóvel (CIB) e CCIR | LRP art. 176, § 1º, II, 3, a | ✓ consertado no LT03 — o modelo não imprimia o CIB |
| proprietário: nome e CPF | LRP art. 176, § 1º, II, 4 | ✓ |
| proprietário: nacionalidade, estado civil, profissão, domicílio | LRP art. 176, § 1º, II, 4; CN-MA art. 479, I | ✓ consertado no LT03 — a tela «Nova matrícula» e «Cadastrar o proprietário da abertura» não tinham o campo; passaram a ter |
| registro anterior | LRP art. 176, § 1º, II, 5; CN-MA art. 479, III | ✓ |
| fecho e subscrição da abertura | CN-MA art. 458 | ✓ |
| selo da abertura | CN-MA arts. 130, § 2º, e 131 | ✓ |

### Registro (R) e averbação (AV) — termo na matrícula

Modelo da casa: `RI_FICHA`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| R-/AV- com o número de ordem e o da matrícula | LRP art. 232 | ✓ |
| título da transmissão ou do ônus (natureza) | LRP art. 176, § 1º, III, 3 | ✓ |
| número e data do protocolo no início do ato | CN-MA arts. 443, § 1º, e 458 | ✓ |
| partes, forma do título e valor (no teor) | LRP art. 176, § 1º, III, 2, 4 e 5 | ✓ |
| data e subscrição de quem praticou | CN-MA art. 458 | ✓ |
| selo do ato | CN-MA arts. 130, § 2º, e 131 | ✓ |
| ato cancelado marcado, sem apagar | LRP arts. 248 e 250 | ✓ |

### Fecho do registro e da averbação

Modelo da casa: `RI_FECHO_DO_ATO`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| lugar e data por extenso | CN-MA art. 458 | ✓ |
| a fé do ato | Lei 8.935/1994, art. 3º | ✓ |
| quem subscreve, com a função | CN-MA art. 458; Lei 8.935/1994, arts. 20 e 21 | ✓ |

### Timbre da ficha da matrícula

Modelo da casa: `RI_CABECALHO`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| a serventia e os delegatários | Lei 8.935/1994, art. 20 | ✓ |
| a matrícula e o CNM no alto da ficha | CNN arts. 330 e 331 | ✓ |
| o livro | LRP art. 173, II | ✓ |

### Certidão de inteiro teor da matrícula

Modelo da casa: `RI_CERTIDAO_INTEIRO_TEOR` (com o molde `RI_CERTIDAO`).

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| a forma | LRP art. 19, caput e § 1º | ✓ |
| o requerente | CN-MA art. 551 | ✓ |
| a matrícula, o livro e o CNM | LRP art. 18; CNN art. 330 | ✓ |
| a abertura da ficha estruturada, como o termo | LRP art. 19, § 11 | ✓ consertado no LT03 — a ficha sem teor saía sem a abertura na certidão |
| o teor de cada ato | LRP art. 19, § 11 | ✓ |
| o fecho de cada ato | LRP art. 19, § 11; CN-MA art. 458 | ✓ consertado no LT03 — o miolo não imprimia o fecho do ato |
| o selo de cada ato e o da abertura | CN-MA art. 131 | ✓ |
| o encerramento do teor | LRP art. 19 | ✓ |
| os títulos prenotados em aberto | LRP art. 21; CN-MA art. 553, § 4º | ✓ |
| a finalidade | CN-MA arts. 549 e 551 | ✓ |
| a validade de 30 dias | CN-MA art. 553 | ✓ |
| a validade com o artigo vigente | CN-MA art. 553 | ✓ consertado no LH13 (21/10/2026) — nota abaixo |
| a data da emissão | LRP art. 19 | ✓ |

> **a validade com o artigo vigente** — consertado no LH13 (o oficial, 21/10/2026, «14 a»): o padrão cita o art. 553 do Código de Normas da CGJ/TJMA (Prov. COGEX 28/2026: a certidão «consignará a validade de 30 (trinta) dias») — o art. 53 trata da sentença na suscitação de dúvida; as certidões do Livro 2 já emitidas guardam o teor que tinham.

### Certidão de ônus reais e de ações reipersecutórias

Modelo da casa: `RI_CERTIDAO_ONUS` (com o molde `RI_CERTIDAO`).

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| a serventia | Lei 8.935/1994, art. 20 | ✓ |
| o imóvel | LRP art. 19, § 9º | ✓ |
| o proprietário vigente | LRP art. 19, § 9º | ✓ |
| os ônus: ato, natureza, data e texto | LRP art. 19, § 9º | ✓ |
| as ações reais e pessoais reipersecutórias | CN-MA art. 558 | ✓ |
| a validade com o artigo vigente | CN-MA art. 553 | ✓ consertado no LH13 (21/10/2026) — nota abaixo |

> **a validade com o artigo vigente** — consertado no LH13 (o oficial, 21/10/2026, «14 a»): o padrão cita o art. 553 do Código de Normas da CGJ/TJMA (Prov. COGEX 28/2026: a certidão «consignará a validade de 30 (trinta) dias») — o art. 53 trata da sentença na suscitação de dúvida; as certidões do Livro 2 já emitidas guardam o teor que tinham.

### Certidão de propriedade

Modelo da casa: `RI_CERTIDAO_PROPRIEDADE` (com o molde `RI_CERTIDAO`).

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| o imóvel | LRP art. 19, § 9º | ✓ |
| o proprietário vigente | LRP art. 19, § 9º | ✓ |
| a afirmação da propriedade | LRP art. 19, § 9º | ✓ |

### Certidão da cadeia dominial

Modelo da casa: `RI_CERTIDAO_DOMINIAL` (com o molde `RI_CERTIDAO`).

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| as transmissões em ordem, com ato, data, natureza e teor | LRP art. 19; CN-MA art. 556 | ✓ |

### Certidão vintenária

Modelo da casa: `RI_CERTIDAO_VINTENARIA` (com o molde `RI_CERTIDAO`).

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| o período e as transmissões e ônus nele | LRP art. 19; CN-MA art. 556 | ✓ |

### Certidão negativa (Indicadores Real e Pessoal)

Modelo da casa: `RI_CERTIDAO_NEGATIVA_IMOVEL`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| a serventia | Lei 8.935/1994, art. 20 | ✓ |
| o requerente | CN-MA arts. 549, III, e 551 | ✓ |
| o parâmetro da busca no texto | CN-MA arts. 554, parágrafo único, e 557 | ✓ |
| o resultado total da busca | CN-MA art. 555 | ✓ |
| a ressalva da matrícula ou transcrição de descrição diversa (busca pelo Indicador Real) | CN-MA art. 554 | ✓ consertado no LT03 — o modelo não tinha a ressalva |
| a finalidade | CN-MA art. 549, III | ✓ |
| data e hora da emissão e validade | CN-MA art. 553 | ✓ |
| quem lavrou, com a função | LRP art. 19 | ✓ |
| a validade com o artigo vigente | CN-MA art. 553 | ✓ consertado no LH13 (21/10/2026) — nota abaixo |

> **a validade com o artigo vigente** — consertado no LH13 (o oficial, 21/10/2026, «14 a»): o padrão cita o art. 553 do Código de Normas da CGJ/TJMA (Prov. COGEX 28/2026: a certidão «consignará a validade de 30 (trinta) dias») — o art. 53 trata da sentença na suscitação de dúvida; as certidões do Livro 2 já emitidas guardam o teor que tinham.

### Nota devolutiva

Modelo da casa: `RI_NOTA`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| o número da nota | CN-MA art. 41 | ✓ |
| o papel timbrado da serventia | CN-MA art. 41 | ✓ |
| o título devolvido: protocolo e data | LRP art. 198; CN-MA art. 44 | ✓ |
| o apresentante, a matrícula e o objeto | LRP art. 198 | ✓ |
| as exigências, de uma só vez e articuladas | LRP art. 198; CN-MA art. 41, § 3º | ✓ |
| a fundamentação | CN-MA art. 41, §§ 1º e 2º | ✓ |
| o procedimento: reapresentar no prazo, mesmo número | CN-MA arts. 41, § 1º, e 44 | ✓ |
| a ressalva da suscitação de dúvida | LRP art. 198, VI | ✓ |
| a data | LRP art. 198 | ✓ |
| identificação e assinatura do oficial ou preposto | LRP art. 198; CN-MA art. 41 | ✓ |

### Certidão de inteiro teor do Livro 3

Modelo da casa: `RI_LIVRO3_CERTIDAO`, `RI_LIVRO3_CERTIDAO_FECHO`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| o livro e o número do registro | LRP arts. 177 e 19 | ✓ |
| a natureza | LRP art. 178 | ✓ |
| o título | LRP art. 178 | ✓ |
| a prenotação | CN-MA art. 443, § 1º | ✓ |
| as partes | LRP art. 176, § 1º, III, 2 | ✓ |
| o teor | LRP art. 19, § 1º | ✓ |
| os atos posteriores | LRP art. 21 | ✓ |
| o encerramento, a finalidade e a validade | LRP art. 19; CN-MA arts. 549 e 553 | ✓ |
| lugar, data e quem expediu | LRP art. 19 | ✓ |
| a autenticidade | LRP art. 19, § 5º | ✓ |
| a validade com o artigo vigente | CN-MA art. 553 | ✓ consertado no LH13 (21/10/2026) — nota abaixo |

> **a validade com o artigo vigente** — consertado no LH13 (o oficial, 21/10/2026, «14 a»): o padrão cita o art. 553 do Código de Normas da CGJ/TJMA (Prov. COGEX 28/2026: a certidão «consignará a validade de 30 (trinta) dias») — o art. 53 trata da sentença na suscitação de dúvida; as certidões do Livro 2 já emitidas guardam o teor que tinham.

### Registro no Livro 3 — a ficha

Modelo da casa: `RI_LIVRO3_FICHA`.

| Elemento obrigatório | Fundamento | Situação |
|---|---|---|
| o número de ordem, a natureza e o título | LRP arts. 177 e 178 | ✓ |
| as partes e o teor | LRP art. 178 | ✓ |
| a prenotação e o CNM | CN-MA art. 443, § 1º; CNN art. 330 | ✓ |
| cada ato com a data e o selo | CN-MA arts. 131 e 458 | ✓ |
| quem praticou o ato (subscrição) | CN-MA art. 458 | ✓ consertado no LH13 (21/10/2026) — nota abaixo |

> **quem praticou o ato (subscrição)** — consertado no LH13 (o oficial, 21/10/2026, «15 a»): o ato grava, na lavratura, o nome, a função e o artigo de quem está logado (`ra_atos.lavrado_*`, como o Livro 2), e cada ato sai na ficha com «Cidade/UF, data. Dou fé. A Escrevente Autorizada (NOME).» (`RI_FECHO_DO_ATO`, CN-MA art. 458); o ato lavrado antes sai sem fecho, porque não se deduz quem foi.

### Os 25 modelos de ato da casa (`ri_modelos_atos.MODELOS`)

Eles moram no código (não em `modelos_padrao/`): são o texto que o botão do
modelo põe na caixa de teor da lavratura. O termo do ato é esse texto, com o
cabeçalho da ficha (`RI_FICHA`: rótulo, natureza, protocolo e data) e o fecho
(`RI_FECHO_DO_ATO`: lugar, data, «Dou fé», quem praticou com a função).

| Espécie | Elemento obrigatório | Fundamento | Situação |
|---|---|---|---|
| Registro (os 12 `R-*`) | o rótulo `{{ rotulo }}` | LRP art. 232 | ✓ nos 12 |
| Registro | a frase do protocolo `{{ protocolo_frase }}` | CN-MA arts. 443, § 1º, e 458 | ✓ nos 12 |
| Registro | as partes (`{{ adquirentes }}`, `{{ transmitentes }}` ou `{{ proprietarios_frase }}`), qualificadas | LRP art. 176, § 1º, III, 2; CN-MA art. 479 | ✓ nos 12 |
| Registro | a forma do título e a procedência (escritura, carta, formal, cédula, contrato, título, sentença, ata) | LRP art. 176, § 1º, III, 4 | ✓ nos 12 |
| Registro | o valor (`[VALOR…]`/`[PRECO…]`) | LRP art. 176, § 1º, III, 5 | ✓ nos 12 |
| Registro | a data e a subscrição | LRP art. 176, § 1º, III, 1; CN-MA art. 458 | ✓ pelo fecho do ato |
| Averbação (os 13 `AV-*`) | o rótulo e a frase do protocolo | LRP art. 232; CN-MA art. 458 | ✓ nos 13 |

> **[CAMPO] por preencher** — ✓ consertado no LD03 (21/10/2026). A
> lavratura recusa, antes de tomar número e pedir selo, o `[CAMPO]` e a
> `{ESCOLHA}` do modelo informado em `modelo_codigo` que ficaram no teor, e o
> marcador que a parte fixa escreve quando o sistema não sabe
> («[INFORMAR O PROTOCOLO]», «[QUALIFICAR AS PARTES]», «[DESCREVER…]», o do
> adquirente) — LRP art. 176, § 1º, III; CN-MA art. 458
> (`ri_modelos_atos.por_preencher`). O colchete que não é do modelo (o acervo
> transcrito tem «[rubrica]») continua indo ao livro. Testes:
> `test_a_lavratura_recusa_o_campo_do_modelo_que_ficou_por_preencher`,
> `test_o_colchete_que_nao_e_do_modelo_continua_indo_ao_livro`,
> `test_todo_colchete_que_a_parte_fixa_escreve_a_lavratura_reconhece` e, na
> tela do modelo, `test_a_tela_do_modelo_nao_manda_ao_livro_campo_do_modelo_em_branco`.

### O que a lavratura e o cancelamento garantem — LD03 (21/10/2026)

| Papel | Elemento | Fundamento | Situação |
|---|---|---|---|
| Certidão de propriedade e de ônus | o proprietário vigente, depois da transmissão | LRP art. 19, § 9º; CN-MA art. 553 | ✓ consertado no LD03 — a lavratura faz titular pela régua única (`ri_correcoes.PAPEL_DE_TITULAR`: proprietário, adquirente, nu-proprietário) e tira do quadro quem transmitiu, com o ato de pé (`test_a_certidao_de_propriedade_depois_da_venda_afirma_o_comprador`, `test_a_venda_lavrada_troca_o_titular_no_quadro_e_avisa_quem_saiu`) |
| Averbação de cancelamento (LRP arts. 248 e 250) | o selo no ato | CN-MA art. 130, § 2º | ✓ consertado no LD03 — nasce selada; o selo que não sai desfaz o cancelamento inteiro (`test_a_averbacao_de_cancelamento_ja_nasce_selada`, `test_o_cancelamento_cujo_selo_nao_sai_nao_fica_de_pe_e_o_ato_continua_valendo`) |
| Todo ato do Livro 2 | o selo no ato (o selo recusado suspende o ato) | CN-MA art. 130, § 2º | ✓ consertado no LD03 — a suspensão falhava no PostgreSQL quando a prenotação já estava amarrada ao ato (chave estrangeira), e o ato ficava sem selo (`test_a_venda_que_o_selo_recusou_nao_fica_no_livro_e_o_vendedor_continua_dono`) |

A venda de **parte ideal** (o vendedor continua condômino; o sistema não guarda
a fração) se acerta em «Partes → Corrigir» (titular, com motivo), e a tela da
lavratura avisa. Se a casa quer uma marca própria na lavratura, é pergunta ao
oficial (LD03).

**Quem é o transmitente no quadro — LD10 (21/10/2026).** O proprietário
vigente (LRP art. 19, § 9º) só muda por quem se identifica: pelo CPF/CNPJ
quando o ato e o quadro o têm; pelo nome só quando nenhum dos dois tem e há um
único titular com aquele nome. O homônimo e o documento de um lado só **não
tiram ninguém** do quadro — a certidão afirmaria que o dono deixou de ser —, e
a lavratura diz isso no recado e na auditoria, com o caminho do conserto
(«Partes → Corrigir»). Testes: `test_o_vendedor_sem_cpf_no_ato_fica_no_quadro_e_a_tela_e_a_auditoria_avisam`
e as regras em `tests/test_ri_correcoes.py`.

As duas pendências do RI que eram **decisão do oficial** (perguntas do
LD03) foram respondidas em 21/10/2026 e consertadas no LH13: **14 a** — a
validade das certidões cita o art. 553; **15 a** — o Livro 3 grava quem
praticou o ato e a ficha o fecha como a do Livro 2.

### O que a matriz não cobre, e por quê

- **Certidão de transcrição** (LRP art. 19, § 10, III; CN-MA art. 548, IV) e
  **certidão de prenotação**: não existem no sistema — não há livro de
  transcrições nem rota de certidão da prenotação (só o comprovante). Ver
  `docs/COBERTURA_FLUXOS.md`.
- **Encerramento diário do Livro 1** (LRP art. 184; CN-MA art. 444, § 1º): o
  Livro 1 do RI é a lista eletrônica; não há termo de encerramento diário.
## Registro de Títulos e Documentos e Registro Civil das Pessoas Jurídicas (LT05, 20/10/2026)

> «os modelos têm de abarcar o que a LEI e as NORMAS exigem» — o oficial,
> 20/10/2026.

**As fontes, nesta ordem de prevalência:** Lei 6.015/1973 (LRP), Títulos III
(RCPJ, arts. 114 a 126) e IV (RTD, arts. 127 a 166), e as disposições gerais
das certidões (arts. 14, 16 a 21); Lei 8.935/1994; Código Civil, art. 1.181
(livros das pessoas jurídicas); o Código Nacional de Normas (Prov. CNJ
149/2023 e alterações — o Livro II trata do RTD/RCPJ quase só da alienação
fiduciária de móveis e da Central RTDPJ, sem regra de conteúdo do termo ou da
certidão); e o Código de Normas Extrajudicial do MA (Prov. COGEX 28/2026,
«CN-MA»): RCPJ nos arts. 398 a 423, RTD nos arts. 953 a 994, selo nos arts.
130 a 135 e nota devolutiva no art. 41. Os textos estão em
`referencia/normas/lei_6015_compilada.txt`, `referencia/normas/cnn_prov_149_2023.txt`
e `referencia/codigo_de_normas_extrajudicial_ma.txt`.

**Como se lê a matriz.** Cada linha é um elemento obrigatório de um papel, com o
artigo. ✓ quer dizer que o papel montado com um contexto completo traz o rótulo
e o valor E que o modelo padrão da casa (`modelos_padrao/rcpj_rtd/`) tem o campo
— é o que `tests/test_requisitos_rtd_rcpj.py` confere, linha por linha, com o
mesmo montador que a tela chama. ⚠ **falta** é defeito do modelo, com teste em
`xfail(strict=True)`: o dia em que o modelo ganhar o campo, o teste avisa. A
maior parte das faltas não se consertava numa frase — **faltava o DADO**: a
casa não guardava sede, fins, diretoria, valor, prazo, partes nem testemunhas
do título. **O LD09 (21/10/2026) as consertou**: o protocolo e o apresentante
saem do título; o extrato do Livro C, as indicações do art. 120 e a matrícula
do periódico são declarações que quem lavra escreve na ficha do título (ou do
registro novo), gravadas no próprio ato (`rg_atos.declaracoes`), e não no
cadastro — a segunda via diz o mesmo que a primeira; o total de páginas do
Livro F é a conta das folhas; o número da averbação é o do ato. Cada uma é uma
linha do padrão que sai do termo quando o ato não tem o dado.

**O livro e a folha no alto do termo — leitura conjunta (LH13, 21/10/2026).**
A LRP art. 133 manda escrever «na parte superior de cada página do livro» o
título, a letra com o número e o ano em que começar (e o art. 135, parágrafo
único; no RCPJ, o CN-MA art. 408, § 3º). A ordem do oficial de 11/09/2026
tirou do cabeçalho o livro, a folha, a série e a ficha, e as 7 linhas
ficaram em `xfail` até a pergunta 28 (`relatorios/LD09.perguntas.md`). A
resposta, literal: «28 tem que ser lida em conjunto com outras normas,
inclusive estaduais que permitem que esses livros sejam digitais, nao fazendo
sentido colocar livro e folha». O livro do RTD/RCPJ desta casa é digital: o
art. 133 se cumpre pelo que identifica o ato no meio digital — a serventia, o
CNS e a atribuição no alto, o número de ordem no CERTIFICO, e o livro, a folha
e o número na etiqueta colada no título, na certidão e no Livro de Protocolo. As 7
linhas viraram o registro da decisão: o teste confere que o cabeçalho NÃO
cita livro nem folha, e que a tela de Modelos continua recusando o ajuste
que os ponha (`rg_teor_rtdpj.cabecalho_tem_livro_ou_folha`).

«Por analogia» marca o elemento do RCPJ que a lei só escreve para o RTD (a
escrituração do RTD é detalhada na LRP, arts. 132 a 155; a do RCPJ não).
O art. 977 do CN-MA (identificação da serventia nas folhas e nas certidões) é
do capítulo do RTD; no RCPJ vale pela mesma razão — a certidão é «autenticada
pelo oficial» (LRP art. 19).

**O que não está na matriz, e por quê.** A notificação por carta com AR e por
edital (CN-MA arts. 990 e 991) e a certidão do RCPJ em resumo e em informação
específica (CN-MA art. 420, I e III) não têm papel nenhum na casa — estão em
`docs/COBERTURA_FLUXOS.md` como ato que falta. O termo de cancelamento, a
certidão negativa (serviços 314 e 315) e o breve relato do RCPJ (art. 420, II)
entraram no LD05 (21/10/2026), com papel próprio e linhas na matriz. A etiqueta dos selos vindos de fora
(`RCPJ_RTD_ETIQUETA_SELO_EXTERNO`) não é ato desta casa.

### A matriz — 288 elementos em 26 papéis; nenhum falta (7 são decisão do oficial)


#### Termo de registro integral — RTD, Livro B

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133; CN-MA art. 977 | ✓ `{unit_short}` em RTD_TEOR_REGISTRO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RTD_TEOR_REGISTRO |
| a atribuição (o título do livro) | LRP art. 133 | ✓ `{atribuicao}` em RTD_TEOR_REGISTRO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP arts. 133 e 135, parágrafo único | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP arts. 136, 1º, e 153; CN-MA art. 973 | ✓ `{numero}` em RTD_TEOR_REGISTRO |
| a espécie do lançamento | LRP art. 146; CN-MA art. 966, III | ✓ `REGISTRADO` em RTD_TEOR_REGISTRO |
| a natureza do título | LRP arts. 135, 3º, e 146; CN-MA art. 966, II | ✓ `{natureza_ato}` em RTD_TEOR_REGISTRO |
| a trasladação do documento, que o termo encerra | LRP art. 142 e § 1º; CN-MA art. 980 | ✓ `arquivado em sua íntegra` em RTD_TEOR_REGISTRO |
| quem subscreve e assina, com a função | LRP arts. 142, § 1º, e 152; CN-MA art. 972 | ✓ `{full_name}` em RTD_TEOR_REGISTRO, `{funcao}` em RTD_TEOR_REGISTRO |
| o local e a data do ato | LRP art. 152 («datado»); CN-MA art. 972 | ✓ `{cidade}` em RTD_TEOR_REGISTRO, `{data_extenso}` em RTD_TEOR_REGISTRO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data do protocolo (da apresentação), antes do registro | LRP art. 136 | ✓ `{data_protocolo}`, `{protocolo}` em RTD_TEOR_REGISTRO — lidos do título (`rg_titulos`) pela rota (`rg_registro.dados_do_termo`) (LD09) |
| o nome do apresentante, antes do registro | LRP arts. 136 e 146; CN-MA art. 966, IV | ✓ `{apresentante}` em RTD_TEOR_REGISTRO — lido do título (`rg_titulos`) pela rota (LD09) |

#### Termo de registro por extrato — RTD, Livro C

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133; CN-MA art. 977 | ✓ `{unit_short}` em RTD_TEOR_REGISTRO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RTD_TEOR_REGISTRO |
| a atribuição (o título do livro) | LRP art. 133 | ✓ `{atribuicao}` em RTD_TEOR_REGISTRO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP arts. 133 e 135, parágrafo único | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP arts. 136, 1º, e 153; CN-MA art. 973 | ✓ `{numero}` em RTD_TEOR_REGISTRO |
| a espécie do lançamento | LRP art. 146; CN-MA art. 966, III | ✓ `REGISTRADO` em RTD_TEOR_REGISTRO |
| a natureza do título | LRP arts. 135, 3º, e 146; CN-MA art. 966, II | ✓ `{natureza_ato}` em RTD_TEOR_REGISTRO |
| a trasladação do documento, que o termo encerra | LRP art. 142 e § 1º; CN-MA art. 980 | ✓ `arquivado em sua íntegra` em RTD_TEOR_REGISTRO |
| quem subscreve e assina, com a função | LRP arts. 142, § 1º, e 152; CN-MA art. 972 | ✓ `{full_name}` em RTD_TEOR_REGISTRO, `{funcao}` em RTD_TEOR_REGISTRO |
| o local e a data do ato | LRP art. 152 («datado»); CN-MA art. 972 | ✓ `{cidade}` em RTD_TEOR_REGISTRO, `{data_extenso}` em RTD_TEOR_REGISTRO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data do protocolo (da apresentação), antes do registro | LRP art. 136 | ✓ `{data_protocolo}`, `{protocolo}` em RTD_TEOR_REGISTRO — lidos do título (`rg_titulos`) pela rota (`rg_registro.dados_do_termo`) (LD09) |
| o nome do apresentante, antes do registro | LRP arts. 136 e 146; CN-MA art. 966, IV | ✓ `{apresentante}` em RTD_TEOR_REGISTRO — lido do título (`rg_titulos`) pela rota (LD09) |
| no registro por extrato: o valor | LRP art. 143; CN-MA art. 981, II | ✓ `{valor}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| no registro por extrato: o prazo | LRP art. 143; CN-MA art. 981, II | ✓ `{prazo}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| no registro por extrato: o lugar da celebração | LRP art. 143; CN-MA art. 981, II | ✓ `{lugar}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| no registro por extrato: o nome e a condição jurídica das partes | LRP art. 143; CN-MA art. 981, III | ✓ `{partes}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| no registro por extrato: as testemunhas | LRP art. 143; CN-MA art. 981, IV | ✓ `{testemunhas}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| no registro por extrato: o reconhecimento de firma e o tabelião | LRP art. 143; CN-MA art. 981, VI | ✓ `{reconhecimento}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| no registro por extrato: o imposto pago | LRP art. 143; CN-MA art. 981, VIII | ✓ `{imposto}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |

#### Termo de registro facultativo para conservação — RTD, Livro F

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133; CN-MA art. 977 | ✓ `{unit_short}` em RTD_TEOR_REGISTRO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RTD_TEOR_REGISTRO |
| a atribuição (o título do livro) | LRP art. 133 | ✓ `{atribuicao}` em RTD_TEOR_REGISTRO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP arts. 133 e 135, parágrafo único | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP arts. 136, 1º, e 153; CN-MA art. 973 | ✓ `{numero}` em RTD_TEOR_REGISTRO |
| a espécie do lançamento | LRP art. 146; CN-MA art. 966, III | ✓ `REGISTRADO` em RTD_TEOR_REGISTRO |
| a natureza do título | LRP arts. 135, 3º, e 146; CN-MA art. 966, II | ✓ `{natureza_ato}` em RTD_TEOR_REGISTRO |
| a trasladação do documento, que o termo encerra | LRP art. 142 e § 1º; CN-MA art. 980 | ✓ `arquivado em sua íntegra` em RTD_TEOR_REGISTRO |
| quem subscreve e assina, com a função | LRP arts. 142, § 1º, e 152; CN-MA art. 972 | ✓ `{full_name}` em RTD_TEOR_REGISTRO, `{funcao}` em RTD_TEOR_REGISTRO |
| o local e a data do ato | LRP art. 152 («datado»); CN-MA art. 972 | ✓ `{cidade}` em RTD_TEOR_REGISTRO, `{data_extenso}` em RTD_TEOR_REGISTRO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data do protocolo (da apresentação), antes do registro | LRP art. 136 | ✓ `{data_protocolo}`, `{protocolo}` em RTD_TEOR_REGISTRO — lidos do título (`rg_titulos`) pela rota (`rg_registro.dados_do_termo`) (LD09) |
| o nome do apresentante, antes do registro | LRP arts. 136 e 146; CN-MA art. 966, IV | ✓ `{apresentante}` em RTD_TEOR_REGISTRO — lido do título (`rg_titulos`) pela rota (LD09) |
| o número total de páginas registradas | LRP art. 127-A, § 3º | ✓ `{paginas}` em RTD_TEOR_REGISTRO — a conta das folhas que o PDF traslada (LD09) |

#### Termo de inscrição de pessoa jurídica — RCPJ, Livro A

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133, por analogia; CN-MA art. 406 | ✓ `{unit_short}` em RCPJ_TEOR_REGISTRO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RCPJ_TEOR_REGISTRO |
| a atribuição (o título do livro) | LRP art. 133, por analogia | ✓ `{atribuicao}` em RCPJ_TEOR_REGISTRO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP art. 133, por analogia; CN-MA art. 408, § 3º | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP art. 120, caput; CN-MA art. 409 | ✓ `{numero}` em RCPJ_TEOR_REGISTRO |
| a espécie do lançamento | LRP art. 120, caput (a espécie do ato); CN-MA art. 409 | ✓ `REGISTRADO` em RCPJ_TEOR_REGISTRO |
| a natureza do título | LRP art. 120, caput; CN-MA art. 409 | ✓ `{natureza_ato}` em RCPJ_TEOR_REGISTRO |
| a trasladação do documento, que o termo encerra | LRP art. 121; CN-MA art. 406 (lançamento vinculado às imagens) | ✓ `arquivado em sua íntegra` em RCPJ_TEOR_REGISTRO |
| quem subscreve e assina, com a função | Lei 8.935/1994, art. 20; LRP art. 142, § 1º, por analogia | ✓ `{full_name}` em RCPJ_TEOR_REGISTRO, `{funcao}` em RCPJ_TEOR_REGISTRO |
| o local e a data do ato | LRP art. 152, por analogia; CN-MA art. 408, § 1º | ✓ `{cidade}` em RCPJ_TEOR_REGISTRO, `{data_extenso}` em RCPJ_TEOR_REGISTRO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data do protocolo (da apresentação), antes do registro | LRP art. 120, caput, e 126 | ✓ `{data_protocolo}`, `{protocolo}` em RCPJ_TEOR_REGISTRO — lidos do título (`rg_titulos`) pela rota (`rg_registro.dados_do_termo`) (LD09) |
| o nome do apresentante, antes do registro | LRP art. 120, VI («nome e residência do apresentante»), e 126 | ✓ `{apresentante}` em RCPJ_TEOR_REGISTRO — lido do título (`rg_titulos`) pela rota (LD09) |
| a indicação do art. 120, I: a denominação, os fins, a sede e a duração | LRP art. 120, I; CN-MA art. 409 | ✓ `{denominacao}`, `{fundo_social}`, `{fins}`, `{sede}`, `{duracao}` em RCPJ_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| a indicação do art. 120, II: o modo de administração e representação | LRP art. 120, II; CN-MA art. 409 | ✓ `{administracao}` em RCPJ_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| a indicação do art. 120, III: se o estatuto é reformável e de que modo | LRP art. 120, III; CN-MA art. 409 | ✓ `{reforma}` em RCPJ_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| a indicação do art. 120, IV: se os membros respondem subsidiariamente | LRP art. 120, IV; CN-MA art. 409 | ✓ `{responsabilidade}` em RCPJ_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| a indicação do art. 120, V: as condições de extinção e o destino do patrimônio | LRP art. 120, V; CN-MA art. 409 | ✓ `{extincao}` em RCPJ_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| a indicação do art. 120, VI: os fundadores e a diretoria, qualificados | LRP art. 120, VI; CN-MA art. 409 | ✓ `{fundadores}`, `{diretoria}` em RCPJ_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |

#### Termo de matrícula de periódico, oficina ou radiodifusão — RCPJ, Livro B

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133, por analogia; CN-MA art. 406 | ✓ `{unit_short}` em RCPJ_TEOR_REGISTRO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RCPJ_TEOR_REGISTRO |
| a atribuição (o título do livro) | LRP art. 133, por analogia | ✓ `{atribuicao}` em RCPJ_TEOR_REGISTRO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP art. 133, por analogia; CN-MA art. 408, § 3º | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP art. 120, caput; CN-MA art. 409 | ✓ `{numero}` em RCPJ_TEOR_REGISTRO |
| a espécie do lançamento | LRP art. 120, caput (a espécie do ato); CN-MA art. 409 | ✓ `REGISTRADO` em RCPJ_TEOR_REGISTRO |
| a natureza do título | LRP art. 120, caput; CN-MA art. 409 | ✓ `{natureza_ato}` em RCPJ_TEOR_REGISTRO |
| a trasladação do documento, que o termo encerra | LRP art. 121; CN-MA art. 406 (lançamento vinculado às imagens) | ✓ `arquivado em sua íntegra` em RCPJ_TEOR_REGISTRO |
| quem subscreve e assina, com a função | Lei 8.935/1994, art. 20; LRP art. 142, § 1º, por analogia | ✓ `{full_name}` em RCPJ_TEOR_REGISTRO, `{funcao}` em RCPJ_TEOR_REGISTRO |
| o local e a data do ato | LRP art. 152, por analogia; CN-MA art. 408, § 1º | ✓ `{cidade}` em RCPJ_TEOR_REGISTRO, `{data_extenso}` em RCPJ_TEOR_REGISTRO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data do protocolo (da apresentação), antes do registro | LRP art. 120, caput, e 126 | ✓ `{data_protocolo}`, `{protocolo}` em RTD_TEOR_REGISTRO — lidos do título (`rg_titulos`) pela rota (`rg_registro.dados_do_termo`) (LD09) |
| o nome do apresentante, antes do registro | LRP art. 120, VI («nome e residência do apresentante»), e 126 | ✓ `{apresentante}` em RTD_TEOR_REGISTRO — lido do título (`rg_titulos`) pela rota (LD09) |
| na matrícula do periódico: o título do periódico e a sede da redação | LRP art. 123, I, a | ✓ `{titulo_periodico}`, `{sede_redacao}`, `{oficinas}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| na matrícula do periódico: o diretor ou redator-chefe | LRP art. 123, I, b | ✓ `{diretor}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |
| na matrícula do periódico: o proprietário | LRP art. 123, I, c | ✓ `{proprietario}` em RTD_TEOR_REGISTRO — declaração da ficha do título, gravada no ato (`rg_atos.declaracoes`) (LD09) |

#### Termo de averbação — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133; CN-MA art. 977 | ✓ `{unit_short}` em RTD_TEOR_AVERBACAO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RTD_TEOR_AVERBACAO |
| a atribuição (o título do livro) | LRP art. 133 | ✓ `{atribuicao}` em RTD_TEOR_AVERBACAO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP arts. 133 e 135, parágrafo único | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP arts. 136, 1º, e 153; CN-MA art. 973 | ✓ `{numero}` em RTD_TEOR_AVERBACAO |
| a espécie do lançamento | LRP art. 146; CN-MA art. 966, III | ✓ `AVERBADO` em RTD_TEOR_AVERBACAO |
| a natureza do título | LRP arts. 135, 3º, e 146; CN-MA art. 966, II | ✓ `{natureza_ato}` em RTD_TEOR_AVERBACAO |
| a trasladação do documento, que o termo encerra | LRP art. 142 e § 1º; CN-MA art. 980 | ✓ `arquivado em sua íntegra` em RTD_TEOR_AVERBACAO |
| quem subscreve e assina, com a função | LRP arts. 142, § 1º, e 152; CN-MA art. 972 | ✓ `{full_name}` em RTD_TEOR_AVERBACAO, `{funcao}` em RTD_TEOR_AVERBACAO |
| o local e a data do ato | LRP art. 152 («datado»); CN-MA art. 972 | ✓ `{cidade}` em RTD_TEOR_AVERBACAO, `{data_extenso}` em RTD_TEOR_AVERBACAO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data da assinatura do documento averbado | LRP art. 128 (a ocorrência que altera o registro); ordem do oficial de 11/09/2026 | ✓ `{data_assinatura}` em RTD_TEOR_AVERBACAO |
| o número de ordem da própria averbação | LRP arts. 149 e 153; CN-MA art. 968 | ✓ `{numero_averbacao}` em RTD_TEOR_AVERBACAO — o número de ordem do ato, no cabeçalho (LD09) |

#### Termo de averbação — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133, por analogia; CN-MA art. 406 | ✓ `{unit_short}` em RCPJ_TEOR_AVERBACAO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RCPJ_TEOR_AVERBACAO |
| a atribuição (o título do livro) | LRP art. 133, por analogia | ✓ `{atribuicao}` em RCPJ_TEOR_AVERBACAO |
| o livro e a folha FORA do alto do termo (decisão do oficial de 21/10/2026) | LRP art. 133, por analogia; CN-MA art. 408, § 3º | ✓ **decisão do oficial** (21/10/2026, pergunta 28, LH13) — o alto do termo NÃO cita livro nem folha: a LRP art. 133 se lê com as normas que permitem o livro digital, inclusive estaduais, e no livro digital não faz sentido; o teste confere a ausência e a recusa da tela de Modelos |
| o número de ordem do registro | LRP art. 120, caput; CN-MA art. 409 | ✓ `{numero}` em RCPJ_TEOR_AVERBACAO |
| a espécie do lançamento | LRP art. 120, caput (a espécie do ato); CN-MA art. 409 | ✓ `AVERBADO` em RCPJ_TEOR_AVERBACAO |
| a natureza do título | LRP art. 120, caput; CN-MA art. 409 | ✓ `{natureza_ato}` em RCPJ_TEOR_AVERBACAO |
| a trasladação do documento, que o termo encerra | LRP art. 121; CN-MA art. 406 (lançamento vinculado às imagens) | ✓ `arquivado em sua íntegra` em RCPJ_TEOR_AVERBACAO |
| quem subscreve e assina, com a função | Lei 8.935/1994, art. 20; LRP art. 142, § 1º, por analogia | ✓ `{full_name}` em RCPJ_TEOR_AVERBACAO, `{funcao}` em RCPJ_TEOR_AVERBACAO |
| o local e a data do ato | LRP art. 152, por analogia; CN-MA art. 408, § 1º | ✓ `{cidade}` em RCPJ_TEOR_AVERBACAO, `{data_extenso}` em RCPJ_TEOR_AVERBACAO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo | CN-MA art. 132 | ✓ `{endereco}` em RCPJ_RTD_PDF_MOLDURA |
| os emolumentos do ato, no próprio documento | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a data da assinatura do documento averbado | LRP art. 128 (a ocorrência que altera o registro); ordem do oficial de 11/09/2026 | ✓ `{data_assinatura}` em RCPJ_TEOR_AVERBACAO |
| o número de ordem da própria averbação | LRP arts. 149 e 153; CN-MA art. 968 | ✓ `{numero_averbacao}` em RCPJ_TEOR_AVERBACAO — o número de ordem do ato, no cabeçalho (LD09) |

#### Certidão de inteiro teor por texto — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia que certifica | CN-MA art. 977; LRP art. 19 | ✓ `sv.unit_name` em RCPJ_RTD_CERTIDAO_ODT |
| o oficial | LRP art. 19 («autenticada pelo oficial») | ✓ `sv.serventia_titular` em RCPJ_RTD_CERTIDAO_ODT |
| o CNS | CN-MA art. 977 | ✓ `sv.ri_cns` em RCPJ_RTD_CERTIDAO_ODT |
| o número da certidão | controle da casa (at_certidoes) | ✓ `c.numero` em RCPJ_RTD_CERTIDAO_ODT |
| o livro, com o número do volume | LRP art. 18 | ✓ `{livro}` em RCPJ_CERTIDAO__onde, `{registro}` em RCPJ_CERTIDAO__onde |
| a folha | LRP art. 18 | ✓ `{folha}` em RCPJ_CERTIDAO__onde_folha |
| o número de ordem do ato | LRP art. 18 | ✓ `{numero}` em RCPJ_CERTIDAO__onde_ato |
| a data do registro | LRP art. 18 | ✓ `{data}` em RCPJ_CERTIDAO__onde_data |
| a natureza do registro | CN-MA art. 420, I (RCPJ); LRP art. 19 | ✓ `{natureza}` em RTD_CERTIDAO |
| o inteiro teor do termo | LRP arts. 19, § 1º, e 161; CN-MA art. 420, IV | ✓ `{teor}` em RTD_CERTIDAO |
| as averbações, cada uma com o seu número | LRP arts. 19 e 128 | ✓ `{ordem}` em RCPJ_CERTIDAO__averbacao, `{teor}` em RCPJ_CERTIDAO__averbacao |
| o local e a data da emissão | LRP art. 19 | ✓ `hoje` em RCPJ_RTD_CERTIDAO_ODT |
| quem assina | LRP art. 19 | ✓ `sv.serventia_titulo` em RCPJ_RTD_CERTIDAO_ODT |
| a impressão digital (autenticidade) | LRP art. 19, § 5º (identificação segura) | ✓ `c.hash_certidao` em RCPJ_RTD_CERTIDAO_ODT |
| o selo da certidão | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo (QR e endereço) | CN-MA art. 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da certidão | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| o selo de cada ato reproduzido | CN-MA art. 131; LRP art. 19, § 1º | ✓ `{selos}` em RCPJ_CERTIDAO__selo_do_ato (LD05) |

#### Certidão de inteiro teor por texto — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia que certifica | CN-MA art. 977; LRP art. 19 | ✓ `sv.unit_name` em RCPJ_RTD_CERTIDAO_ODT |
| o oficial | LRP art. 19 («autenticada pelo oficial») | ✓ `sv.serventia_titular` em RCPJ_RTD_CERTIDAO_ODT |
| o CNS | CN-MA art. 977 | ✓ `sv.ri_cns` em RCPJ_RTD_CERTIDAO_ODT |
| o número da certidão | controle da casa (at_certidoes) | ✓ `c.numero` em RCPJ_RTD_CERTIDAO_ODT |
| o livro, com o número do volume | LRP art. 18 | ✓ `{livro}` em RCPJ_CERTIDAO__onde, `{registro}` em RCPJ_CERTIDAO__onde |
| a folha | LRP art. 18 | ✓ `{folha}` em RCPJ_CERTIDAO__onde_folha |
| o número de ordem do ato | LRP art. 18 | ✓ `{numero}` em RCPJ_CERTIDAO__onde_ato |
| a data do registro | LRP art. 18 | ✓ `{data}` em RCPJ_CERTIDAO__onde_data |
| a natureza do registro | CN-MA art. 420, I (RCPJ); LRP art. 19 | ✓ `{natureza}` em RCPJ_CERTIDAO |
| o inteiro teor do termo | LRP arts. 19, § 1º, e 161; CN-MA art. 420, IV | ✓ `{teor}` em RCPJ_CERTIDAO |
| as averbações, cada uma com o seu número | LRP arts. 19 e 128 | ✓ `{ordem}` em RCPJ_CERTIDAO__averbacao, `{teor}` em RCPJ_CERTIDAO__averbacao |
| o local e a data da emissão | LRP art. 19 | ✓ `hoje` em RCPJ_RTD_CERTIDAO_ODT |
| quem assina | LRP art. 19 | ✓ `sv.serventia_titulo` em RCPJ_RTD_CERTIDAO_ODT |
| a impressão digital (autenticidade) | LRP art. 19, § 5º (identificação segura) | ✓ `c.hash_certidao` em RCPJ_RTD_CERTIDAO_ODT |
| o selo da certidão | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
| a consulta do selo (QR e endereço) | CN-MA art. 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da certidão | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| o selo de cada ato reproduzido | CN-MA art. 131; LRP art. 19, § 1º | ✓ `{selos}` em RCPJ_CERTIDAO__selo_do_ato (LD05) |

#### Certidão só das averbações — RTD e RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o objeto: as averbações, e não o registro | LRP art. 19 (a certidão do que foi pedido) | ✓ `{teor}` em RCPJ_RTD_CERTIDAO_SO_AVERBACOES |
| o registro a que se referem, com livro e número | LRP art. 18 | ✓ `{onde}` em RCPJ_RTD_CERTIDAO_SO_AVERBACOES |

#### Certidão por reprodução (PDF) — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia e o CNS | CN-MA art. 977 | ✓ `{unit_short}` em RTD_CERTIDAO_CAPA, `{cns}` em RTD_CERTIDAO_CAPA |
| o oficial | LRP art. 19 | ✓ `{oficial}` em RTD_CERTIDAO_CAPA |
| o número e a data do registro | LRP art. 18 | ✓ `{numero}` em RTD_CERTIDAO_CAPA, `{data_registro}` em RTD_CERTIDAO_CAPA |
| o protocolo e a data da apresentação | LRP arts. 135 e 146 | ✓ `{protocolo}` em RTD_CERTIDAO_CAPA, `{data_apresentacao}` em RTD_CERTIDAO_CAPA |
| o livro, com o volume | LRP art. 18 | ✓ `{livro}` em RTD_CERTIDAO_CAPA |
| quantas páginas reproduz | LRP art. 19, § 1º (reprografia) | ✓ `{paginas}` em RTD_CERTIDAO_CAPA, `{paginas_extenso}` em RTD_CERTIDAO_CAPA |
| a denominação e a natureza | CN-MA art. 420 | ✓ `{denominacao}` em RTD_CERTIDAO_CAPA, `{natureza}` em RTD_CERTIDAO_CAPA |
| o local, a data e quem subscreve | LRP art. 19 | ✓ `{data_extenso}` em RTD_CERTIDAO_CAPA, `{full_name}` em RTD_CERTIDAO_CAPA |
| o selo da certidão e a consulta | CN-MA arts. 131 e 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da certidão | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |

#### Certidão por reprodução (PDF) — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia e o CNS | CN-MA art. 977 | ✓ `{unit_short}` em RCPJ_CERTIDAO_CAPA, `{cns}` em RCPJ_CERTIDAO_CAPA |
| o oficial | LRP art. 19 | ✓ `{oficial}` em RCPJ_CERTIDAO_CAPA |
| o número e a data do registro | LRP art. 18 | ✓ `{numero}` em RCPJ_CERTIDAO_CAPA, `{data_registro}` em RCPJ_CERTIDAO_CAPA |
| o protocolo e a data da apresentação | LRP arts. 135 e 146 | ✓ `{protocolo}` em RCPJ_CERTIDAO_CAPA, `{data_apresentacao}` em RCPJ_CERTIDAO_CAPA |
| o livro, com o volume | LRP art. 18 | ✓ `{livro}` em RCPJ_CERTIDAO_CAPA |
| quantas páginas reproduz | LRP art. 19, § 1º (reprografia) | ✓ `{paginas}` em RCPJ_CERTIDAO_CAPA, `{paginas_extenso}` em RCPJ_CERTIDAO_CAPA |
| a denominação e a natureza | CN-MA art. 420 | ✓ `{denominacao}` em RCPJ_CERTIDAO_CAPA, `{natureza}` em RCPJ_CERTIDAO_CAPA |
| o local, a data e quem subscreve | LRP art. 19 | ✓ `{data_extenso}` em RCPJ_CERTIDAO_CAPA, `{full_name}` em RCPJ_CERTIDAO_CAPA |
| o selo da certidão e a consulta | CN-MA arts. 131 e 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da certidão | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |

#### Certidão de notificação positiva — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia e o oficial | CN-MA art. 977 | ✓ desenhado pelo sistema na impressão |
| o registro do documento notificado (número e livro) | CN-MA art. 988, § 2º (não há certidão antes do registro); LRP art. 160, § 1º | ✓ `{onde}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA |
| o destinatário, com o documento | CN-MA art. 986 | ✓ `{destinatario}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA, `{documento}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA |
| o endereço da diligência | CN-MA arts. 986, § 3º, e 987, § 2º | ✓ `{endereco}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA |
| o local e a data da certidão | LRP art. 19 | ✓ `{cidade}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA, `{data_extenso}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA |
| quem expediu | LRP art. 19 (autenticada pelo oficial) | ✓ desenhado pelo sistema na impressão |
| o selo da certidão, com QR e consulta | CN-MA arts. 130 a 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da certidão | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| o dia e a hora em que se notificou | CN-MA art. 986, § 4º | ✓ `{data_da_notificacao}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA, `{hora_da_notificacao}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA |
| como se efetivou (entrega, recusa ou procurador) | CN-MA arts. 986 e 992 | ✓ `{como}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA, `entregando-lhe` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA__entregue |

#### Certidão de notificação negativa — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia e o oficial | CN-MA art. 977 | ✓ desenhado pelo sistema na impressão |
| o registro do documento notificado (número e livro) | CN-MA art. 988, § 2º (não há certidão antes do registro); LRP art. 160, § 1º | ✓ `{onde}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA |
| o destinatário, com o documento | CN-MA art. 986 | ✓ `{destinatario}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA, `{documento}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA |
| o endereço da diligência | CN-MA arts. 986, § 3º, e 987, § 2º | ✓ `{endereco}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA |
| o local e a data da certidão | LRP art. 19 | ✓ `{cidade}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA, `{data_extenso}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA |
| quem expediu | LRP art. 19 (autenticada pelo oficial) | ✓ desenhado pelo sistema na impressão |
| o selo da certidão, com QR e consulta | CN-MA arts. 130 a 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da certidão | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| as três diligências, em dias e horários alternados | CN-MA art. 987, § 2º | ✓ `{quantas}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA, `{diligencias}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA, `{data}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__ida, `{hora}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__ida |

#### Averbação da notificação positiva — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a averbação à margem: quem, quando e a certidão | CN-MA arts. 986, § 2º, e 987, §§ 1º e 4º; LRP art. 160, § 1º | ✓ `{data_da_notificacao}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA__averbacao, `{certidao}` em RTD_CERTIDAO_NOTIFICACAO_POSITIVA__averbacao |

#### Averbação da notificação negativa — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a averbação à margem: as diligências e a certidão | CN-MA arts. 986, § 2º, e 987, §§ 1º, 2º e 4º | ✓ `{quantas}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__averbacao, `{certidao}` em RTD_CERTIDAO_NOTIFICACAO_NEGATIVA__averbacao |

#### Termo de abertura do livro contábil — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o livro (tipo e número de ordem) | CC art. 1.181; CN-MA art. 402, V | ✓ `{tipo_livro}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{numero_livro}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |
| a pessoa jurídica e o CNPJ | CC art. 1.181; CN-MA art. 402, V | ✓ `{pj_nome}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{pj_cnpj}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |
| as folhas e a numeração | CC art. 1.181 (termos de abertura e encerramento) | ✓ `{folhas}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{folha_de}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{folha_ate}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |
| o número do controle da autenticação | CN-MA art. 402, V | ✓ `{numero}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{ano}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |
| o local, a data e quem assina | CN-MA art. 972 (datado e assinado) | ✓ `{cidade_uf}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{data_extenso}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{full_name}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |
| o selo, conferível no papel (número, QR e consulta) | CN-MA arts. 130 a 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da autenticação | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a serventia que autentica, com o CNS | CN-MA art. 977 | ✓ `{unit_name}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA, `{cns}` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |
| a finalidade do livro | CC art. 1.181 | ✓ `destina-se` em RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA |

#### Termo de encerramento do livro contábil — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o livro (tipo e número de ordem) | CC art. 1.181; CN-MA art. 402, V | ✓ `{tipo_livro}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{numero_livro}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO |
| a pessoa jurídica e o CNPJ | CC art. 1.181; CN-MA art. 402, V | ✓ `{pj_nome}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{pj_cnpj}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO |
| as folhas e a numeração | CC art. 1.181 (termos de abertura e encerramento) | ✓ `{folhas}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{folha_de}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{folha_ate}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO |
| o número do controle da autenticação | CN-MA art. 402, V | ✓ `{numero}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{ano}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO |
| o local, a data e quem assina | CN-MA art. 972 (datado e assinado) | ✓ `{cidade_uf}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{data_extenso}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO, `{full_name}` em RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO |
| o selo, conferível no papel (número, QR e consulta) | CN-MA arts. 130 a 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da autenticação | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |

#### Certidão da autenticação de livro — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o livro (tipo e número de ordem) | CC art. 1.181; CN-MA art. 402, V | ✓ `{tipo_livro}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{numero_livro}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |
| a pessoa jurídica e o CNPJ | CC art. 1.181; CN-MA art. 402, V | ✓ `{pj_nome}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{pj_cnpj}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |
| as folhas e a numeração | CC art. 1.181 (termos de abertura e encerramento) | ✓ `{folhas}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{folha_de}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{folha_ate}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |
| o número do controle da autenticação | CN-MA art. 402, V | ✓ `{numero}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{ano}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |
| o local, a data e quem assina | CN-MA art. 972 (datado e assinado) | ✓ `{cidade_uf}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{data_extenso}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{full_name}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |
| o selo, conferível no papel (número, QR e consulta) | CN-MA arts. 130 a 132 | ✓ desenhado pelo sistema na impressão |
| os emolumentos da autenticação | LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |
| a serventia que autentica, com o CNS | CN-MA art. 977 | ✓ `{unit_name}` em RCPJ_LIVRO_CONTABIL_CERTIDAO, `{cns}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |
| o selo citado no texto da certidão | CN-MA art. 131 | ✓ `{selo}` em RCPJ_LIVRO_CONTABIL_CERTIDAO |

#### Termo de cancelamento — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133; CN-MA art. 977 | ✓ `{unit_short}` em RTD_TEOR_CANCELAMENTO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RTD_TEOR_CANCELAMENTO |
| o registro cancelado, com o número | LRP art. 165; CN-MA art. 994, § 1º | ✓ `CANCELADO` em RTD_TEOR_CANCELAMENTO, `{numero}` em RTD_TEOR_CANCELAMENTO |
| a causa do cancelamento e o documento que o autorizou | LRP art. 165 («a razão dele, mencionando-se o documento que o autorizou»); CN-MA art. 994, § 1º | ✓ `{motivo}` em RTD_TEOR_CANCELAMENTO |
| quem subscreve e assina, com a função | LRP art. 165 («assinando»); CN-MA art. 994, § 1º | ✓ `{full_name}` em RTD_TEOR_CANCELAMENTO, `{funcao}` em RTD_TEOR_CANCELAMENTO |
| o local e a data | LRP art. 165 («datando»); CN-MA art. 994, § 1º | ✓ `{cidade}` em RTD_TEOR_CANCELAMENTO, `{data_extenso}` em RTD_TEOR_CANCELAMENTO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |

#### Termo de cancelamento — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia, no alto da folha | LRP art. 133, por analogia; CN-MA art. 406 | ✓ `{unit_short}` em RCPJ_TEOR_CANCELAMENTO |
| o CNS da serventia | CN-MA art. 977 (identificação da serventia) | ✓ `{cns}` em RCPJ_TEOR_CANCELAMENTO |
| o registro cancelado, com o número | LRP art. 165; CN-MA art. 994, § 1º | ✓ `CANCELADO` em RCPJ_TEOR_CANCELAMENTO, `{numero}` em RCPJ_TEOR_CANCELAMENTO |
| a causa do cancelamento e o documento que o autorizou | LRP art. 165 («a razão dele, mencionando-se o documento que o autorizou»); CN-MA art. 994, § 1º | ✓ `{motivo}` em RCPJ_TEOR_CANCELAMENTO |
| quem subscreve e assina, com a função | LRP art. 165 («assinando»); CN-MA art. 994, § 1º | ✓ `{full_name}` em RCPJ_TEOR_CANCELAMENTO, `{funcao}` em RCPJ_TEOR_CANCELAMENTO |
| o local e a data | LRP art. 165 («datando»); CN-MA art. 994, § 1º | ✓ `{cidade}` em RCPJ_TEOR_CANCELAMENTO, `{data_extenso}` em RCPJ_TEOR_CANCELAMENTO |
| o selo de fiscalização, no corpo do ato | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |

#### Certidão negativa — RTD

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o nome pesquisado | CN-MA art. 963, § 3º (pelo nome das partes) | ✓ `{nome}` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| o CPF ou CNPJ pesquisado | CN-MA art. 963, IV e § 3º (o documento de identificação no indicador) | ✓ `{documento}` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| os livros pesquisados | LRP art. 19 (a certidão do que foi pedido) | ✓ `{registro}` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| que nada consta, nem registro nem averbação | LRP arts. 16 e 17 | ✓ `NÃO CONSTA` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| a serventia que certifica | CN-MA art. 977; LRP art. 19 | ✓ `sv.unit_name` em RCPJ_RTD_CERTIDAO_ODT |
| o número da certidão | controle da casa (at_certidoes) | ✓ `c.numero` em RCPJ_RTD_CERTIDAO_ODT |
| o local e a data da emissão | LRP art. 19 | ✓ `hoje` em RCPJ_RTD_CERTIDAO_ODT |
| quem assina | LRP art. 19 | ✓ desenhado pelo sistema na impressão |
| o selo da certidão, com os emolumentos | CN-MA arts. 130 e 131; LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |

#### Certidão negativa — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o nome pesquisado | CN-MA art. 963, § 3º (pelo nome das partes) | ✓ `{nome}` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| o CPF ou CNPJ pesquisado | CN-MA art. 963, IV e § 3º (o documento de identificação no indicador) | ✓ `{documento}` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| os livros pesquisados | LRP art. 19 (a certidão do que foi pedido) | ✓ `{registro}` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| que nada consta, nem registro nem averbação | LRP arts. 16 e 17 | ✓ `NÃO CONSTA` em RCPJ_RTD_CERTIDAO_NEGATIVA |
| a serventia que certifica | CN-MA art. 977; LRP art. 19 | ✓ `sv.unit_name` em RCPJ_RTD_CERTIDAO_ODT |
| o número da certidão | controle da casa (at_certidoes) | ✓ `c.numero` em RCPJ_RTD_CERTIDAO_ODT |
| o local e a data da emissão | LRP art. 19 | ✓ `hoje` em RCPJ_RTD_CERTIDAO_ODT |
| quem assina | LRP art. 19 | ✓ desenhado pelo sistema na impressão |
| o selo da certidão, com os emolumentos | CN-MA arts. 130 e 131; LRP art. 14, parágrafo único | ✓ desenhado pelo sistema na impressão |

#### Certidão em breve relato — RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a denominação | CN-MA art. 420, II | ✓ `{denominacao}` em RCPJ_CERTIDAO_BREVE_RELATO |
| o endereço da sede | CN-MA art. 420, II | ✓ `{sede}` em RCPJ_CERTIDAO_BREVE_RELATO |
| o número de inscrição no CNPJ | CN-MA art. 420, II | ✓ `{cnpj}` em RCPJ_CERTIDAO_BREVE_RELATO |
| o objeto social | CN-MA art. 420, II | ✓ `{objeto}` em RCPJ_CERTIDAO_BREVE_RELATO |
| o capital social | CN-MA art. 420, II | ✓ `{capital}` em RCPJ_CERTIDAO_BREVE_RELATO |
| os sócios e as participações (com fins lucrativos) | CN-MA art. 420, II | ✓ `{socios}` em RCPJ_CERTIDAO_BREVE_RELATO |
| os membros da diretoria (sem fins lucrativos) | CN-MA art. 420, II | ✓ `{diretoria}` em RCPJ_CERTIDAO_BREVE_RELATO |
| a data do último ato registrado ou averbado | CN-MA art. 420, II | ✓ `{ultimo_ato}` em RCPJ_CERTIDAO_BREVE_RELATO |
| o registro da pessoa jurídica, com livro e número | CN-MA art. 420, II | ✓ `{onde}` em RCPJ_CERTIDAO_BREVE_RELATO |
| a serventia que certifica | CN-MA art. 977; LRP art. 19 | ✓ `sv.unit_name` em RCPJ_RTD_CERTIDAO_ODT |
| o local e a data da emissão | LRP art. 19 | ✓ `hoje` em RCPJ_RTD_CERTIDAO_ODT |
| quem assina | LRP art. 19 | ✓ desenhado pelo sistema na impressão |
| o selo da certidão | CN-MA arts. 130 e 131 | ✓ desenhado pelo sistema na impressão |
#### Nota devolutiva (qualificação negativa) — RTD e RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| o papel timbrado da serventia | CN-MA art. 41 («em papel timbrado do cartório») | ✓ `sv.unit_name` em RCPJ_RTD_NOTA |
| o protocolo do título | CN-MA art. 41; LRP art. 146 | ✓ `t.numero` em RCPJ_RTD_NOTA |
| a data da apresentação | LRP art. 146 | ✓ `apresentado_em` em RCPJ_RTD_NOTA |
| o apresentante | CN-MA art. 966, IV | ✓ `t.apresentante` em RCPJ_RTD_NOTA |
| a natureza do título | CN-MA art. 966, II | ✓ `t.natureza` em RCPJ_RTD_NOTA |
| as exigências, claras e objetivas | CN-MA arts. 41 e 975 | ✓ `q.exigencias` em RCPJ_RTD_NOTA |
| o fundamento legal | CN-MA art. 41, § 1º | ✓ `q.fundamentacao` em RCPJ_RTD_NOTA |
| o prazo e o que fazer | CN-MA art. 41, § 1º (os procedimentos a adotar) | ✓ `prazo_ate` em RCPJ_RTD_NOTA |
| a data | CN-MA art. 41 | ✓ `data_extenso` em RCPJ_RTD_NOTA |
| a identificação e a assinatura de quem qualificou | CN-MA art. 41 | ✓ `oficial` em RCPJ_RTD_NOTA |

#### Etiqueta de registro (declaração no corpo do título) — RTD e RCPJ

| Elemento obrigatório | Fonte | No papel e no modelo |
|---|---|---|
| a serventia | CN-MA art. 977 | ✓ `e.cartorio` em RCPJ_RTD_ETIQUETA |
| o ato, o livro, a folha e o número de ordem | LRP art. 147; CN-MA art. 967, § 1º | ✓ `e.folha` em RCPJ_RTD_ETIQUETA, `e.numero` em RCPJ_RTD_ETIQUETA |
| a data do lançamento | LRP art. 147; CN-MA art. 967, § 1º | ✓ `e.data` em RCPJ_RTD_ETIQUETA |
| o protocolo | CN-MA art. 966, § 1º | ✓ `e.protocolo` em RCPJ_RTD_ETIQUETA |
| o selo, com QR e consulta | CN-MA arts. 130 a 132 | ✓ `e.selo` em RCPJ_RTD_ETIQUETA |
| os emolumentos | LRP art. 14, parágrafo único | ✓ `e.valores` em RCPJ_RTD_ETIQUETA |
| quem rubrica, com a função | LRP art. 147 («rubricando o oficial») | ✓ `e.oficial` em RCPJ_RTD_ETIQUETA |

## Tabelionato de Protesto (LT04, 20/10/2026)

O que cada papel do Protesto tem de trazer, elemento por elemento, com o artigo.
As fontes vão na ordem de prevalência que o oficial deu:

1. **Lei 9.492/1997**, em `referencia/normas/lei_9492_protesto.txt`;
2. **Código Nacional de Normas** (Prov. CNJ 149/2023, compilado até o Prov. CN
   253, de 18/08/2026), em `referencia/normas/cnn_prov_149_2023.txt`;
3. **Código de Normas do MA** (Prov. COGEX 28/2026), em
   `referencia/codigo_de_normas_extrajudicial_ma.txt`. O capítulo do Protesto são
   os arts. 881 a 952, e o selo os arts. 130 a 135.

A tabela abaixo é a `MATRIZ` de `tests/test_requisitos_protesto.py`, e cada
linha vira dois testes:

- o papel, montado com um contexto completo, traz o elemento;
- o modelo padrão (`modelos_padrao/protesto/`) tem o campo.

Legenda: ✓ o papel e o modelo têm o elemento; ⚠ defeito (`xfail(strict=True)`
com o artigo).

### Registro do protesto (o termo lavrado, `pt_atos.teor`, modelo `PT_TERMO_PROTESTO` e peça `PT_TERMO_QUALIFICACAO`)

Desde o LD04 (21/10/2026), a peça `PT_TERMO_QUALIFICACAO` vai NO ALTO do
termo: é o «acima mencionado e qualificado» do texto da casa, com a redação do
instrumento. É peça, e não claro do modelo, para o termo que a casa
personalizou também a receber (Lei 9.492, art. 21, § 4º).

| Elemento | Artigo | Situação |
|---|---|---|
| número de ordem e data do registro | CN-MA art. 914, I | ✓ `{lugar}` e `{data}` (LD04) |
| data e número da protocolização | Lei 9.492 art. 22, I; CN-MA art. 914 | ✓ `{protocolo}` (LD04) |
| nome (e endereço) do apresentante | Lei 9.492 art. 22, II; CN-MA art. 914, III | ✓ `{apresentante}` (LD04); desde o LD08, com o endereço — o mesmo pedaço do instrumento (`apresentante_endereco`) |
| reprodução, ou as indicações do título | Lei 9.492 art. 22, III | ✓ `{titulo}` e `{credor}` (LD04) |
| certidão das intimações | Lei 9.492 art. 22, IV; CN-MA art. 914 | ✓ `{edital}`: pessoal, por edital ou eletrônica |
| devedor, documento e endereço | Lei 9.492 arts. 21, § 4º, e 22, VII | ✓ `{devedor}`, todos os devedores (LD04) |
| intervenientes e aceite por honra | Lei 9.492 art. 22, V e VI | só na letra de câmbio, sem campo (`protesto_instrumento.ITENS_DO_ART_22`) |
| data e assinatura do tabelião | Lei 9.492 art. 22, VIII | ⚠ não há papel do livro |
| tipo do protesto | Lei 9.492 art. 23; CN-MA art. 914, IX | ✓ `{tipo}` |
| motivo do protesto | Lei 9.492 arts. 21 e 23; CN-MA arts. 914 e 916 | ✓ `{motivo}` |

### Instrumento de protesto (`PT_INSTRUMENTO_PROTESTO` e `PT_INSTRUMENTO_DESCRICAO`)

| Elemento | Artigo | Situação |
|---|---|---|
| a serventia que declara | Lei 9.492 art. 20 | ✓ `{serventia}` |
| nº de ordem e data do registro; livro e folha | CN-MA art. 914, I | ✓ `registro` |
| data e número da protocolização | Lei 9.492 art. 22, I | ✓ `protocolo_com_data` |
| nome do apresentante | Lei 9.492 art. 22, II | ✓ `apresentante` — o da CRA e, desde o LD04, o que o balcão informa |
| endereço do apresentante | Lei 9.492 art. 22, II | ✓ `apresentante_endereco` (LD08): o endereço do título (o balcão o pede, CN-MA art. 884, I) ou do cadastro dos apresentantes, pelo código da CRA — o arquivo da Central não o traz. Sem nenhum dos dois, o papel diz só o nome e a conferência do art. 22 marca o item II |
| indicações do título: espécie, nº, emissão, vencimento, valor e valor protestado | Lei 9.492 art. 22, III | ✓ `titulo` |
| menção à cópia arquivada, ou a falta dela | Lei 9.492 art. 22, parágrafo único | ✓ `{copia}` |
| certidão das intimações | Lei 9.492 art. 22, IV | ✓ `{intimacao}`: em mãos, por edital e, desde o LD04, a eletrônica (`PT_INSTRUMENTO_INTIMACAO_DIGITAL`), igual à do termo |
| credor e documento | CN-MA art. 914 | ✓ `credor_com_documento` |
| devedor, documento e endereço | Lei 9.492 art. 22, VII | ✓ `devedor`, `devedor_documento`, `devedor_endereco` |
| tipo e motivo | Lei 9.492 art. 23; CN-MA art. 914, IX | ✓ `tipo_e_motivo` |
| local, data e assinatura | Lei 9.492 art. 22, VIII | ✓ `PT_MOLDURAS.local_e_data` e o titular no papel |
| selo, com código e consulta | CN-MA arts. 130 a 132 | ✓ é o carimbo do selo do ato de protesto, com QR e link |

### Aviso de intimação (`PT_AVISO_INTIMACAO`)

| Elemento | Artigo | Situação |
|---|---|---|
| número do protocolo | CN-MA art. 920; Lei 9.492 art. 14, § 2º | ✓ |
| devedor: nome, documento e endereço | CN-MA arts. 906 e 920 | ✓ |
| espécie por extenso, número, valor e vencimento | CN-MA art. 920 | ✓ |
| aceite | CN-MA art. 920 | ✓ |
| sacador ou favorecido (o credor), com CPF/CNPJ | CN-MA arts. 920 e 923 | ✓ |
| apresentante | CN-MA arts. 920 e 923 | ✓ o da CRA e, desde o LD04, o que o balcão informa |
| CPF/CNPJ do apresentante | CN-MA art. 923; CNN art. 356, § 4º | ✓ `{documento_do_apresentante}` (LD08): o do título (balcão) ou o do cadastro dos apresentantes, pelo código da CRA |
| prazo-limite | CN-MA arts. 920 e 925, § 4º | ✓ |
| endereço, horário e telefone do tabelionato | CN-MA arts. 920 e 923 | ✓ |

### Edital de intimação (`PT_EDITAL_INTIMACAO`)

| Elemento | Artigo | Situação |
|---|---|---|
| nome e identificação do devedor | CN-MA art. 922, § 3º; Lei 9.492 art. 15 | ✓ |
| identificação do título (protocolo, número, espécie) | CN-MA art. 922, § 3º | ✓ |
| valor a pagar e prazo-limite | CN-MA art. 922, § 3º | ✓ |
| tabelionato, endereço e telefone | CN-MA art. 922, § 3º | ✓ |

### Livro de Protocolo (a vista montada dos atos; colunas em `PT_MOLDURAS`)

| Elemento | Artigo | Situação |
|---|---|---|
| nº de ordem, protocolo e data | Lei 9.492 art. 32; CN-MA arts. 907 e 908 | ✓ |
| natureza, valor, apresentante, devedor | Lei 9.492 art. 32; CN-MA art. 908 | ✓ |
| CPF/CNPJ do devedor | CN-MA art. 906 | ✓ coluna própria, a última — as de antes ficam no mesmo lugar para quem lê por posição (`PT_MOLDURAS.protocolo_documento`, LD04; no fim desde o LD11) |
| ocorrências com data | CN-MA art. 908, §§ 1º e 5º | ✓ (`PT_LIVRO_PROTOCOLO`) |
| informação e certidão só a pedido escrito do devedor ou por ordem judicial | CN-MA arts. 905, parágrafo único, e 906, § 2º | ✓ com a autorização, a certidão de protesto traz o parágrafo do Livro de Protocolo (`PT_CERTIDAO_LINHA`: `protocolo_abertura`, `apontamento`, `titulo_apontado`, `ocorrencias`; LD04); com o CPF/CNPJ, casa pelo documento, e o nome — sem curinga — só acha, inteiro, o devedor gravado sem documento, com aviso ao escrevente (LD12); sem documento no pedido, pelo nome (`protesto_certidao.onde_casa_o_devedor`, LD11) |

### Quitação do título pago no tabelionato (`PT_QUITACAO`, LD04)

| Elemento | Artigo | Situação |
|---|---|---|
| a quitação, no ato do pagamento | Lei 9.492 art. 19, § 2º; CN-MA art. 927 | ✓ `/protesto/pagamentos/<ato>/quitacao.odt`, na linha do pagamento da ficha; só para quem lança o pagamento (ADMIN, MANAGER, USER — LD11) |
| depois do lançamento no Livro de Pagamentos | CN-MA art. 930, § 1º | ✓ só sai do pagamento lançado (o anulado recusa), e diz o livro, a folha e o número |
| devedor, valor, título, protocolo e credor | Lei 9.492 art. 19 | ✓ |
| no cheque, a quitação condicionada à liquidação | Lei 9.492 art. 19, § 3º; CN-MA art. 927, parágrafo único | ✓ `{cheque}` |
| o selo do ato | CN-MA arts. 130 a 132 | ✓ o carimbo do selo do pagamento |

### Termo do cancelamento (`PT_TERMO_CANCELAMENTO`, LD04)

| Elemento | Artigo | Situação |
|---|---|---|
| o termo, em documento apartado | Lei 9.492 art. 26, §§ 5º e 6º | ✓ gravado no ato do cancelamento (`pt_atos.teor`) |
| o registro cancelado (livro, folha, nº e data), o título e os devedores | Lei 9.492 art. 26; CN-MA art. 896 | ✓ a redação do registro e do instrumento |
| a hipótese e o fundamento | Lei 9.492 art. 26, §§ 1º a 4º; CN-MA arts. 942 e 943 | ✓ `{hipotese}`, `{fundamento_legal}` e `{fundamento}` |
| a anotação no índice | Lei 9.492 art. 26, § 6º; CN-MA art. 896 | ✗ não há Livro de Índices |

### Livro de Registro de Pagamentos (`PT_MOLDURAS`, `PT_LIVRO_PAGAMENTOS`)

Os elementos das alíneas a a h do CN-MA art. 930 estão todos presentes (✓):

- a) nº de ordem;
- b) data;
- c) protocolo;
- d) natureza;
- e) valor pago;
- f) emolumentos;
- g) devedor e favorecido;
- h) ocorrências: a forma de pagamento e a identificação.

### Certidão negativa (`PT_CERTIDAO_NEGATIVA`)

| Elemento | Artigo | Situação |
|---|---|---|
| a quem pede | Lei 9.492 art. 31; CN-MA art. 950 | ✓ `{pedido}` |
| nome e CPF/CNPJ | Lei 9.492 art. 27, § 1º; CN-MA art. 906 | ✓ |
| período de cinco anos | Lei 9.492 art. 27; CNN art. 365 | ✓ |
| o resultado | CNN art. 263-K, I | ✓ «NÃO ENCONTREI» |

### Certidão positiva (`PT_CERTIDAO_CABECA`, `PT_CERTIDAO_LINHA`)

A régua é o CNN art. 129, que remete aos dados do art. 259, parágrafo único,
«sempre que disponíveis».

| Elemento | Artigo | Situação |
|---|---|---|
| a quem pede | Lei 9.492 art. 31 | ✓ |
| nome e CPF/CNPJ do devedor | art. 259, p. ú., I e II; CN-MA art. 906 | ✓ |
| livro, folha e número | art. 259, p. ú., III | ✓ |
| ocorrência e data | art. 259, p. ú., IV | ✓ «protestado em» |
| apresentante | art. 259, p. ú., V | ✓ |
| tipo do endosso | art. 259, p. ú., V | ✓ `endosso` (LD08): «endosso translativo» (T) ou «endosso mandato» (M); sem endosso, nada — pergunta 3 de `relatorios/LD08.perguntas.md` |
| credor e CPF/CNPJ | art. 259, p. ú., VI | ✓ |
| número do protocolo | art. 259, p. ú., VII | ✓ |
| data do protocolo | art. 259, p. ú., VII | ✓ `protocolo_com_data` (LD08): a data do apontamento, que é a da protocolização |
| espécie, número, emissão, vencimento | art. 259, p. ú., VII | ✓ |
| valor original e valor protestado | art. 259, p. ú., VII | ✓ |
| valor das intimações e do edital | art. 259, p. ú., VII | não disponível no dado; o próprio artigo diz «sempre que disponíveis» |
| tipo e motivo | art. 259, p. ú., VII; Lei 9.492 art. 30 | ✓ |
| selo da certidão, com QR e consulta; emolumentos que o selo declara | CN-MA arts. 87, XVI, 130 a 132 e 952 | ✓ |

### Certidão de cancelamento (`PT_CERTIDAO_CANCELAMENTO`)

| Elemento | Artigo | Situação |
|---|---|---|
| pedido escrito do devedor, ou a ordem judicial | Lei 9.492 art. 27, § 2º; CN-MA arts. 944 e 948 | ✓ |
| o registro cancelado e a data da baixa | Lei 9.492 art. 26; CN-MA art. 945 | ✓ |
| o fecho do art. 26 | Lei 9.492 art. 26 | ✓ `{fecho}` |

### Certidão com sustação judicial precária

| Elemento | Artigo | Situação |
|---|---|---|
| «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA», os dados do registro, o número do processo, o caráter provisório e o fecho «Resultado emitido em cumprimento à decisão judicial — Processo nº …» | CNN art. 263-K, III | ✓ `sustacao_precaria` + `fecho_precaria` de `PT_CERTIDAO_LINHA` (LH13, 21/10/2026: decisão do oficial, pergunta 18, letra a); a ordem judicial leva a marca do caráter (`pt_atos.ordem_carater`) |
| a decisão DEFINITIVA fica fora da certidão («NADA CONSTA») | CNN art. 263-K, I | ✓ a ordem marcada DEFINITIVA tira só aquele protesto (LH13) |
| a ordem que manda expressamente emitir negativa se cumpre nos exatos limites; no segredo de justiça, só a sustação e o número do processo | CNN art. 263-K, § 1º | ✓ `ordem_manda_negativa` tira só aquele protesto; `sustacao_precaria_em_segredo` de `PT_CERTIDAO_LINHA` (LH13) |
| a ordem lançada antes da marca | (regra de transição da casa, LH13) | fica fora da certidão, como antes, até alguém a marcar; a tela de certidões e a ficha avisam |

### Certidão diária em forma de relação (texto em `protesto_relacao._teor`, sem modelo editável)

| Elemento | Artigo | Situação |
|---|---|---|
| nota de informação reservada | Lei 9.492 art. 29; CN-MA art. 949 | ✓ |
| nome e CPF | CNN art. 130 | ✓ |
| espécie | CNN art. 130 | ✓ |
| data do protesto | CNN art. 130 | ✓ |
| valor protestado | CNN art. 130 | ✓ |
| data do vencimento | CNN art. 130 | ✓ coluna VENCIMENTO (LD04), a última — as oito de antes ficam no mesmo lugar para quem lê por posição (LD11) |

### O que não se conferiu no texto oficial

- O leiaute do selo impresso (posição, texto, QR obrigatório) depende da LC
  estadual 48/2000 e de atos da CGJ-MA que não estão na pasta.
- Os valores da tabela de emolumentos (Lei estadual 9.109/2009) também não estão
  lá: os testes usam preços de mentira.
- O `.txt` do CN-MA tem saltos que não foram conferidos contra o PDF:
  - art. 883, que passa do § 7º ao § 9º;
  - art. 890, sem § 5º;
  - art. 908, sem § 3º.

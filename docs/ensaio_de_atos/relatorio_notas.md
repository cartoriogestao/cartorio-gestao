# Relatório do ensaio de atos — Tabelionato de Notas

Ensaio de 03/11/2026, pedido do oficial de 01/11/2026. O inventário está em `inventario_notas.md`; o
teste em `tests/test_ensaio_de_atos_notas.py` (os casos em `tests/ensaio_de_atos_notas.py`).

**Como foi feito.** Catorze casos, cada um do protocolo pago ao termo, ao traslado e à certidão, pelas
mesmas telas e na mesma ordem de `tests/test_fluxo_notas.py`: abrir o ato pela minuta, ligar ao
protocolo, incluir as partes pelo quadro «Partes», preencher pela minuta (com as cláusulas e as escolhas
de cada situação), lançar no livro. A trava ficou ligada; a única porta aberta foi a do selador de
mentira, em 127.0.0.1 (a lavratura das Notas sela pelo aparelho). `test_fluxo_notas` já praticava cada
minuta com duas pessoas solteiras e maiores; aqui variou **quem comparece**: casado com o cônjuge que
consente, procurador, pessoa jurídica e quem a representa, menor e quem o representa ou assiste, quem não
sabe assinar, testador cego, advogado no inventário e no divórcio, emancipação por um só genitor.

**Resultado.** Os catorze foram ao livro com selo, menos um (item 1, a procuração com «OUTORGADA»).
Estão certos e conferidos: a leitura em voz alta duas vezes ao testador cego (CC art. 1.867), a assinatura
a rogo pela testemunha instrumentária com a impressão digital (CC art. 1.865), a certidão do registro de
imóveis arquivada na procuração para alienar (CC art. 661, § 1º; CN-MA art. 833) e a volta ao nome de
solteira no divórcio. Ficaram **oito defeitos** no teste, em `xfail(strict=True)`, e quatro observações
sem teste. A ordem é a do balcão: o que mais cai primeiro.

Os nomes, os CPF e o CNPJ do ensaio são fictícios. Os artigos do CNN e do CN-MA são os que
`docs/REQUISITOS_LEGAIS.md` já citou; os textos dessas normas não estão nesta máquina.

---

## 1. Quem comparece em nome de outro vai para o lado errado do negócio

**CONSERTADO em 03/11/2026** (conserto liberado pela sessão de PRs): o lado vem da qualidade da CEP
(`notas_teor.lado_da_parte`); quem comparece por outro sai qualificado e marcado, fora dos dois lados,
até o item 2 lhe dar o campo de quem ele representa.

**O que saiu.** A abertura do ato separa as partes em dois lados — outorgantes e outorgados — por
**palavra** na qualificação (`notas_teor.partes_por_lado`, `_SEGUNDA_PARTE`): quem tem «OUTORGADO»,
«COMPRADOR», «DONATARIO» ou «PROCURADOR» vai para o segundo lado; todo o resto, para o primeiro.

| Caso | O que o termo diz |
|---|---|
| Compra e venda com o vendedor representado por procurador | «e como OUTORGADO COMPRADOR, CARLOS EXEMPLO PROCURADOR, …; BEATRIZ EXEMPLO DE SOUZA, …» — o procurador do vendedor é comprador |
| Compra e venda com pessoa jurídica compradora | «como OUTORGANTE VENDEDOR, MARIO …; ANA EXEMPLO SOCIA, …» — quem representa a compradora é vendedora |
| Doação a menor, representado pela mãe | «como OUTORGANTE DOADOR, MARIO …; JOANA EXEMPLO DOS SANTOS, …» — a mãe do donatário é doadora |
| Pacto antenupcial com nubente menor, assistida pela mãe | «como NUBENTES MARIO …; ANA …; JOANA EXEMPLO DOS SANTOS, …» — a mãe é nubente |
| Procuração com «OUTORGADA» | «OUTORGADA» não contém «OUTORGADO»: a outorgada vai para o lado dos outorgantes, o lado dos procuradores fica vazio, e o ato não se lavra («[OUTORGADO(S) — QUALIFIQUE A PARTE NO ATO]»). O mesmo com «DONATÁRIA» |

**A norma.** CC art. 215, § 1º, III (nome e qualificação de cada parte); CN-MA art. 798, V e VI (a
qualificação, e a parte representada com a menção da procuração).

**Por que importa.** É o texto que vai ao livro e ao registro de imóveis: uma escritura que diz que o
procurador do vendedor é comprador não se registra, e corrigi-la é escritura de retificação. A trava da
CENSEC não pega, porque as qualidades («PROCURADOR», «REPRESENTANTE», «ASSISTENTE») são todas válidas na CEP.

**Proposta.** Decidir o lado pela **qualidade da CEP** (`notas_censec.QUALIFICACAO_PARA_CEP`, que já
conhece «OUTORGADA», «COMPRADORA», «DONATÁRIA» etc.), e não por pedaço de palavra. Quem não é lado —
procurador (fora da procuração), representante, assistente, quem assina a rogo — **não entra em lado
nenhum**: sai junto da parte que representa, «neste ato representado(a) por …». Para isso o quadro
«Partes» precisa dizer **quem** cada um representa (item 2). Sem esse campo, o mínimo é tirá-los dos
dois lados e deixar a menção marcada para o escrevente completar.

**No teste:** `test_o_procurador_do_vendedor_nao_vira_comprador`,
`test_o_representante_da_compradora_nao_vira_vendedor`,
`test_a_mae_que_representa_o_donatario_menor_nao_vira_doadora`,
`test_a_assistente_da_nubente_menor_nao_vira_nubente`, `test_a_outorgada_mulher_e_outorgada`.

## 2. A procuração do representado e o assento do menor não têm onde ser ditos

**CONSERTADO em 03/11/2026, por decisão do oficial:** o quadro «Partes» diz quem cada um representa ou
assiste e o instrumento, e a menção vai na qualificação do representado («…, neste ato representado(a)
por FULANO, conforme procuração lavrada no livro X, folha Y, do …»), como no CN-MA art. 798, VI.

**O que saiu.** O quadro «Partes» pede nome, documento, nacionalidade, estado civil, profissão,
identidade, filiação, união estável, cônjuge, regime e endereço. Não tem: de quem a pessoa é
procuradora, representante ou assistente; o livro, a folha e a serventia da procuração; a data de
nascimento e o assento do menor. No ensaio, o único lugar foi o campo livre «Assinantes do ato e a
condição em que assinam» da minuta — que vai ao fecho, e não à qualificação.

**A norma.** CN-MA art. 798, VI («sendo parte representada, menção ao livro, folha e serventia da
procuração e do substabelecimento, que ficam arquivados») e VII («havendo interesse de menor ou incapaz,
menção expressa à data de nascimento, com livro, folha, termo e serventia do assento, e por quem está
assistido ou representado») — os dois como `notas_modelos` os cita.

**Proposta.** Três campos na parte: «representa (parte)», «instrumento da representação» (livro, folha,
serventia; ou o contrato social, para a PJ) e, para o menor, «nascimento e assento». A qualificação
(`notas_teor.qualificar`) passa a montar a frase a partir deles. **Pergunta ao oficial:** a menção da
procuração vai na qualificação do representado (como o CN-MA art. 798, VI, a põe) ou num parágrafo
próprio, como faz o acervo da casa? (A ver no acervo: só a estrutura, nunca nome nem número.)

## 3. O cônjuge que consente sai como mais um vendedor, sem dizer que consente

**CONSERTADO em 03/11/2026, por decisão do oficial:** no imóvel do casal em comunhão, os dois são
outorgantes vendedores e ninguém é anuente (o padrão da casa); o «ANUENTE», onde cabe, sai depois dos
outorgantes com a frase do CC art. 1.647, I, e nunca como vendedor.

**O que saiu.** Na venda do casado em comunhão parcial, o cônjuge com a qualidade «ANUENTE» sai na abertura
como mais um «OUTORGANTE VENDEDOR». O termo não diz que ele consente; «ANUENTE» só aparece cru na linha das
assinaturas («JOANA EXEMPLO DOS SANTOS, ANUENTE»).

**A norma.** CC art. 1.647, I: nenhum dos cônjuges pode, sem autorização do outro (exceto no regime da
separação absoluta), alienar ou gravar de ônus real os bens imóveis.

**Proposta.** A qualidade «ANUENTE» vira frase própria na abertura: «e, como ANUENTE, seu cônjuge …, que
consente na presente venda (art. 1.647, I, do Código Civil)». **Pergunta ao oficial:** quando o imóvel é
comum (comunhão), a casa prefere os dois como vendedores — e então nenhum é anuente — ou o padrão é o
anuente? O ensaio aceita os dois; o que não pode é «ANUENTE» virar vendedor sem a frase.

**No teste:** `test_o_conjuge_do_vendedor_consente_e_o_termo_o_diz`.

## 4. O testamento declara um estado civil, e a parte tem outro

**CONSERTADO em 03/11/2026** (conserto liberado pela sessão de PRs): a escolha, a cláusula do casado e o
cônjuge vêm da parte TESTADOR (`notas_teor.estado_civil_do_testador`), e a vírgula foi para dentro da cláusula.

**O que saiu.** O testador cadastrado como casado (com o cônjuge e o regime) e a escolha da minuta «Estado
civil do testador» deixada em «solteiro»: a qualificação diz «casado com JOANA …» e a primeira disposição
diz «declara chamar-se como acima qualificado e ser solteiro, .». Lavrou sem aviso. O «, .» é a vírgula da
minuta antes do complemento que só existe para o casado.

**A norma.** CC art. 215, § 1º, III, e art. 1.864, I.

**Proposta.** A escolha vem preenchida pelo estado civil da parte (o escrevente só a troca se quiser), a
conferência da lavratura acusa a diferença, e a vírgula vai para dentro da cláusula do casado. O mesmo
padrão vale para as outras minutas que repetem o estado civil numa escolha (a conferir uma a uma).

**No teste:** `test_o_estado_civil_do_testamento_e_o_da_parte`,
`test_o_testamento_nao_deixa_virgula_antes_do_ponto`.

## 5. O advogado do inventário e do divórcio entra como parte

**CONSERTADO em 03/11/2026, por decisão do oficial:** «OAB nº / UF» no quadro «Partes»; o advogado fica
fora das partes, e o «DOS ADVOGADOS» das nove minutas é montado dele (`{{ advogados }}`).

**O que saiu.** Com o advogado incluído no quadro «Partes» (é o que a CESDI pede: `notas_censec`
exige a qualidade «Advogado» no inventário e no divórcio), a abertura o põe entre «as partes a seguir
qualificadas, todas maiores, capazes e concordes», e o parágrafo «DOS ADVOGADOS» pede o advogado de novo
num campo livre da minuta.

**A norma.** CN-MA arts. 808, § 1º, 819 e 822, § 5º (como o LT02 cita): o advogado assiste as partes.

**Proposta.** A qualidade «ADVOGADO» fica fora dos lados (como a testemunha), e o parágrafo «DOS
ADVOGADOS» é montado dele — nome, qualificação e inscrição na OAB —, sem o campo livre.

**No teste:** `test_o_advogado_do_inventario_assiste_e_nao_e_parte`.

## 6. A emancipação por um só genitor fala no plural

**CONSERTADO em 03/11/2026** (conserto liberado pela sessão de PRs): a minuta escolhe o singular ou o
plural pela quantidade de outorgantes (`um_outorgante`, do quadro «Partes»).

**O que saiu.** Com a cláusula «Se um dos pais» e a escolha «a mãe»: «compareceram como OUTORGANTES JOANA
…» e «Declaram os OUTORGANTES que são a mãe do EMANCIPANDO».

**Proposta.** O singular e o plural pelo número de outorgantes, como já faz a procuração
(`NOTAS_ABERTURA_PROCURACAO__um_outorgante` e `__varios_outorgantes`).

**No teste:** `test_a_emancipacao_concedida_so_pela_mae_fala_no_singular`.

## 7. A emancipação não confere os dezesseis anos

**CONSERTADO em 03/11/2026** (conserto liberado pela sessão de PRs): o teor não se monta com menos de
dezesseis anos ou com dezoito. E o lançamento passou a recusar o ato sem teor: o ensaio mostrou que
a emancipação recusada ia ao livro assim mesmo, com folha, termo e selo e sem texto nenhum.

**O que saiu.** O emancipando «nascido em dez de outubro de dois mil e vinte e seis (10/10/2026),
portanto com dezesseis anos completos» — e lavrou.

**A norma.** CC art. 5º, par. ún., I: a concessão dos pais, por instrumento público, ao menor com dezesseis
anos completos.

**Proposta.** A data de nascimento do emancipando vira campo de data, e a lavratura recusa quem não tem
dezesseis anos no dia do ato (e quem já tem dezoito, que não se emancipa).

**No teste:** `test_a_emancipacao_confere_os_dezesseis_anos`.

## 8. A data por extenso diz «tres»

**CONSERTADO em 03/11/2026** (conserto liberado pela sessão de PRs): «três» em `livro_nucleo._UNIDADES`.

**O que saiu.** «aos tres (3) dias do mês de novembro» — em todo ato das Notas lavrado num dia 3 (e no 23).
A palavra vem de `livro_nucleo._UNIDADES`; o motor de modelos tem um conserto próprio
(`modelos_motor_contexto`), que a data da lavratura das Notas não usa.

**Proposta.** «três» na tabela de `livro_nucleo`. Antes, medir quem mais a usa (o RI, o livro de
protocolo) e declarar a troca no ouro onde ela mudar texto.

**No teste:** `test_a_data_por_extenso_tem_acento`.

---

## Observações sem teste

9. **CONSERTADO em 03/11/2026: quem assina por quem, a partir do item 2.** **A linha das assinaturas repete a qualificação crua** — «PEDRO EXEMPLO MENOR, DONATARIO», sem acento e
   com o menor impúbere entre os que assinam. Com o item 2, quem assina pelo menor é o representante.
10. **CONSERTADO em 03/11/2026, por decisão do oficial: «Estado do Maranhão», do cadastro.** **«Estado do MA».** A abertura escreve a sigla onde o CC art. 215, § 1º, I, pede o local do ato. Se for
    padrão da casa, fica; se não, o nome do estado vem do cadastro da serventia. **Pergunta ao oficial.**
11. **CONSERTADO em 03/11/2026: «sabe | pode» é escolha.** **«Motivo: sabe | pode»** no testamento de quem não assina é campo de texto livre depois de «não»: quem
    digitar «não sabe» lavra «não não sabe». Deveria ser escolha (sabe / pode).
12. **CONSERTADO em 03/11/2026: «nome de solteiro(a)».** **«voltará a usar o nome de solteiro»** no divórcio é texto fixo da minuta, no masculino, para quem quer
    que volte ao nome.

## A segunda leva (03/11/2026): CENSEC, DOI, revogação e certidão do testamento

Depois dos consertos dos itens 1 a 12, os mesmos casos foram até as telas que vêm depois do livro: a
fila de remessas da CENSEC (`/notas/remessas/<central>/pendencias`, a quinzena do ato) e a tela única da
DOI da serventia (`/registro-imoveis/doi`, aberta pelo oficial — a do escrevente responde 403). E dois
caminhos novos: a revogação de uma procuração lavrada aqui, e a certidão do testamento pedida por
terceiro.

**Certo e conferido:**
- cada ato vai à central certa (escritura e procuração à CEP, divórcio e inventário à CESDI, testamento
  ao RCTO, e nunca o testamento à CEP), e o que foi à CEP está pronto, porque a CEP trava a lavratura;
- na DOI, os titulares da operação e mais ninguém: o casal em comunhão como dois alienantes; o vendedor
  e não o procurador; a pessoa jurídica e não quem a representa; o menor donatário e não a mãe; o
  cônjuge anuente fora;
- a revogação vinculada pela tela («Vincular») anota a procuração, que passa a REVOGADO e sai revogada
  no traslado e na certidão (CN-MA art. 831; Lei 8.935/1994, art. 6º, II);
- a certidão do testamento pedida por terceiro com o testador vivo é recusada (CN-MA art. 851, § 4º).

### 13. «DOADORA», «DONATÁRIA» e «CESSIONÁRIA» não estão na tabela da CEP

**CONSERTADO em 03/11/2026** (liberado pela sessão de PRs): o feminino na tabela da CEP e na lista da DOI.

**O que saiu.** A doação de JOANA, «DOADORA», a BEATRIZ, «DONATARIA», não foi ao livro: a trava da CEP
recusou as duas qualificações («não corresponde a nenhuma qualidade da CEP»), e o teor ficou sem
outorgado, porque o lado da parte também vem dessa tabela (item 1). A tabela
(`notas_censec.QUALIFICACAO_PARA_CEP`) conhece «OUTORGADA», «VENDEDORA» e «COMPRADORA», mas não o feminino
de doador, donatário, cessionário e usufrutuário. A DOI tem a mesma lacuna por outro caminho: as listas
dela (`notas_doi.QUEM_ADQUIRE`) procuram «OUTORGADO» e «DONATARIO» dentro da qualificação, e «OUTORGADA» e
«DONATARIA» caem em dúvida.

**A norma.** CC art. 215, § 1º, III.

**Proposta.** O feminino de cada palavra das duas tabelas. Não depende de decisão.

**No teste:** `test_a_doadora_e_a_donataria_vao_ao_livro_e_a_doi`.

### 14. Todo divórcio e todo inventário ficam parados na remessa da CESDI

**O que saiu.** O divórcio e o inventário do ensaio foram ao livro e pararam na fila da CESDI: «sem data
do casamento», «regime não está na tabela da CENSEC», «sem o responsável pelos filhos menores», «exige uma
parte Advogado» — com o advogado no quadro —, «exige uma parte Falecido», «qualidade não vale para
Inventário» — e, de cada parte, «falta dataNascimento», «falta sexo», «falta localResidenciaMunicipio». A CESDI lê a qualidade de cada parte de uma coluna própria (`qualidade_cesdi`) que a tela
do ato não preenche, e a data do casamento, o regime e o responsável pelos menores de colunas que também
não têm campo. O próprio código registra a lacuna desde 09/10/2026 (`notas_censec.CENTRAIS_QUE_TRAVAM`,
«não têm onde ser preenchidos na tela do ato»), e por isso a CESDI não trava a lavratura.

**A norma.** CN-MA art. 785 (a remessa) e o layout da CESDI.

**Proposta.** A qualidade da CESDI sair da qualificação, como a da CEP (ADVOGADO → Advogado, HERDEIRO →
Herdeiro, INVENTARIANTE → Inventariante, DIVORCIANDO → Divorciando, VIÚVO → Viúvo); o falecido como parte
do inventário; e a data do casamento, o regime e o responsável pelos menores tirados do que a minuta já
pergunta («[DATA DO CASAMENTO]», «[REGIME DE BENS]»). **Pergunta ao oficial:** o falecido entra no
quadro «Partes» do inventário (como a CESDI quer), ou a casa prefere um campo próprio?

**No teste:** `test_o_divorcio_e_o_inventario_ficam_prontos_para_a_cesdi`.

### 15. Todo testamento fica parado na remessa do RCTO

**CONSERTADO em 03/11/2026, por decisão do oficial:** a mãe e o pai em dois campos, e a data de nascimento,
em toda parte de todos os atos de Notas.

**O que saiu.** «testador sem data de nascimento» e «o RCTO exige o nome da mãe do testador». O quadro
«Partes» não tem a data de nascimento, e a filiação é texto livre.

**Proposta.** A data de nascimento na parte (serve também ao menor do item 2 e ao emancipando do item 7)
e a filiação em dois campos, mãe e pai. **Pergunta ao oficial:** os dois campos da filiação valem para
toda parte, ou só para o testador?

**No teste:** `test_o_testamento_fica_pronto_para_o_rcto`.

## O que não se ensaiou

- Os atos sem minuta (renúncia de herança, reconhecimento de filho, bem de família, divisão de condomínio,
  servidão, ata de mediação, apostila, carta de sentença, atos eletrônicos): ver o inventário.
- O envio às centrais e a geração do arquivo da DOI: a fila e a declaração foram conferidas; o envio
  precisa da rede, que a trava barra.
- A comunicação de veículo e a consulta à CCN: precisam da rede, que a trava barra.

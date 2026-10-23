# O menu de Protesto do E-Ofício, item por item — e o que temos

Levantado em **31/08/2026**, dos dezessete prints que o oficial fez do menu
inteiro, com todos os submenus abertos. É a régua que ele pediu: *"preciso que
tenhamos algo semelhante"*.

**Isto é inventário, e não plano.** O que se constrói, em que ordem, e o que não
se constrói é decisão dele — e alguns itens desta lista **não devem existir**
aqui, por razões que estão marcadas ao lado.

---

## O menu, como o E-Ofício o organiza

Vinte itens no primeiro nível, em cinco blocos separados por linha. A ordem
importa: é a do trabalho, e foi ela que o oficial seguiu ao trazer o roteiro do
dia.

| # | item do E-Ofício | temos? | onde, ou o que falta |
|---|---|---|---|
| 1 | **Protocolar** ▸ | ✅ | o apontamento na ficha do título — `/protesto/<id>/lancar` |
| 2 | **Intimação** ▸ | ⚠️ | ver o quadro abaixo |
| 3 | **Motivo do Protesto** | ❌ | cadastro de motivos; a casa hoje escreve o motivo no ato |
| 4 | **Registrar Ocorrência** ▸ | ⚠️ | ver o quadro abaixo |
| 5 | **Edital** ▸ (Publicar · Eletrônico) | ⚠️ | *Publicar* existe (`.odt` e a folha do dia); **o eletrônico não** |
| 6 | **Consultar Título** (Ctrl+Q) | ✅ | a lista de títulos, que busca por devedor, nome e documento |
| 7 | **Estatística** ▸ | ❌ | cinco relatórios — ver abaixo |
| 8 | **Certidões** ▸ | ⚠️ | negativa, positiva e cancelamento existem; faltam três |
| 9 | **Livros** ▸ | ✅ | o núcleo serve os livros das seis atribuições |
| 10 | **CRA** ▸ | ⚠️ | **cinco de seis** — falta a AC |
| 11 | **CENPROT** ▸ | ❌ | os quatro, e três dependem de medição |
| 12 | **Exportação de Dados** ▸ (Serasa · Boa Vista · CNP Brasil) | ❌ | os birôs de crédito |
| 13 | **SDT** ▸ (Recepção de Arquivo Remessa Particular) | ❌ | a remessa que não vem pela Central |
| 14 | **Web** ▸ (atualiza dados no site da serventia) | ❌ | site próprio; não se aplica hoje |
| 15 | **Relatório** ▸ | ❌ | nove relatórios — dois deles são obrigação com o TJMA |
| 16 | **Banco** ▸ (Arquivo Remessa · Arquivo Retorno) | ❌ | e há dúvida se se aplica — ver abaixo |
| 17 | **Repasse ao Apresentante** | ❌ | o dinheiro que volta para quem apresentou |
| 18 | **Monitoramento de Devedor** ▸ (Registrar · Relatório) | ❌ | |
| 19 | **Orçamento de custas para o protesto** | ⚠️ | a receita medida existe; a tela de orçamento não |
| 20 | **Propriedade** | ✅ | as configurações da atribuição |

---

## Os submenus, e o que cada um traz

### Intimação ▸

| | temos? | |
|---|---|---|
| Devedor (Ctrl+J) | ✅ | o aviso de intimação, com o endereço congelado |
| Tratamento da Entrega | ✅ | a entrega e o motivo da não-entrega, do catálogo medido |
| Demonstrativo da Entrega | ❌ | o relatório do que foi entregue |
| Motivo de Devolução da Intimação | ✅ | os 13 motivos de `tbMotivoNEntrega`, com as duas marcas |
| Entregador de Intimações | ❌ | cadastro de quem entrega — nesta casa é a própria serventia |
| Exportação Eletrônica | ❌ | |
| Digitalização em Lote | ❌ | |
| **Resolve** ▸ | ❌ | **intimação DIGITAL** — Intimação Digital, Histórico das notificações, Cancelar uma Intimação, Demonstrativo de títulos intimados |
| Taxas Adicionais | ❌ | |

> **O «Resolve» é o que mais muda o dia.** Medido nesta casa: **1.092 dos 1.618
> avisos foram publicados por edital**, e **1.068 das 1.139 não-entregas dizem
> «Ausente»** — o normal aqui é não achar ninguém. A intimação digital ataca
> exatamente isso. É integração com serviço de fora, e por isso é pergunta antes
> de ser trabalho: **qual serviço, com que contrato**.

### Registrar Ocorrência ▸

| | temos? | |
|---|---|---|
| **Pagar** ▸ | ✅ | `lancar_pagamento` |
| **Retirar (Desistência)** ▸ Manual (Ctrl+O) | ✅ | |
| **Retirar (Desistência)** ▸ **Via CRA** | ✅ | o quinto layout, de 127 posições |
| Devolver (Ctrl+O) | ⚠️ | a irregularidade se lê do arquivo; **devolver pela tela, não** |
| **Protestar** (Ctrl+F) | ✅ | e agora com a tela «A protestar», do passo da tarde |
| **Cancelar** (Ctrl+X) | ✅ | com hipótese do catálogo **mais** fundamento escrito |
| Retificar | ❌ | |
| **Efeito Suspensivo** | ✅ | **construído em 01/09/2026** — Lei 9.492/1997, art. 17: bloqueia protesto, pagamento e desistência; o revogado vai no alto do «A protestar», com o prazo de um dia útil do § 2º |
| Devolução em Massa | ❌ | |
| Ajustar folha do protesto | ❌ | |
| Converter Protesto Postergado em Normal | ❌ | |

> **O efeito suspensivo era o mais grave desta lista, e foi o primeiro
> construído** — em 01/09/2026, no dia seguinte ao levantamento. Ele vem de
> decisão judicial e impede o protesto; sem ele registrado, a tela «A
> protestar» ofereceria, **em lote**, um título que a Justiça mandou parar.
>
> Ao lê-lo na doutrina apareceram duas coisas que eu não suporia: o § 1º
> bloqueia **três** atos (pago, protestado ou retirado), e o § 2º dá **um dia
> útil** para protestar depois da revogação, **sem nova intimação**.

### Edital ▸ · Certidões ▸ · Livros ▸

| Edital | temos? |
|---|---|
| Publicar | ✅ — com número de exercício, teor congelado, hash e `.odt` |
| **Eletrônico** | ❌ — é o **e-Proclamas/CENPROT**, e o oficial informou em 28/08 que a publicação desta casa é digital, na Central |

| Certidões | temos? |
|---|---|
| Certidão Negativa / Positiva · Negativa · Positiva | ✅ — e o tipo sai **do que a busca achou**, nunca de quem pede |
| Cancelamento | ✅ |
| 2ª Via do Cancelamento | ❌ |
| **2ª Via do Instrumento do Protesto** | ❌ — o instrumento é o papel que prova o protesto |
| Certidão Genérica | ❌ |
| Relação de Títulos | ❌ |

| Livros | temos? |
|---|---|
| Protocolo · Índice de Protesto · Registro de Protesto · Registro de Pagamento | ✅ — pelo núcleo, com o termo em `.odt` |
| Livro de Protocolo Eletrônico ▸ | ⚠️ — o livro existe; a forma «eletrônica» dele não foi medida |

### CRA ▸ — cinco de seis

| | temos? |
|---|---|
| Remessa | ✅ recebe, confere, aponta e confirma |
| Confirmação | ✅ sai automática ao receber |
| Desistência | ✅ o quinto layout |
| Retorno | ✅ |
| **Autorização de cancelamento do protesto – AC** | ❌ — e **medido, não faz falta**: 2 títulos em 1.370. Ver abaixo |
| Andamento | ✅ **desde 31/08/2026**, e agora sai **também ao receber a remessa** |

> **A AC NÃO É IMPORTANTE, E EU DISSE O CONTRÁRIO.** Escrevi aqui que ela era
> *«o buraco mais claro deste levantamento»*, pelo argumento de que o E-Ofício
> a trata em **três telas** — o item de menu, duas estatísticas e um relatório.
>
> **Três telas não são medida de frequência.** O oficial mandou a régua certa
> em 01/09/2026: *«sobre tudo que o e-ofício faz, tente buscar dados dentro do
> banco de dados. Se não encontrar, possivelmente não é importante»*. Medido:
>
> | | |
> |---|---|
> | títulos com `bitAutorizadoCancelamento` | **2 de 1.370** — os dois da Equatorial Maranhão |
> | cancelamentos lavrados pela casa | **54** (8 em 2026, 16 em 2025) |
> | dos quais vieram pela AC | **2** |
>
> **O cancelamento acontece; ele é que não vem pela Central.** A anuência do
> credor chega direto ao balcão — e o oficial confirmou: *«não temos nenhum
> relatório de cancelamento no último ano»*.
>
> `tbBoletoAutorizacaoCancel` tem 2 linhas, e não é o arquivo da CRA: é o
> **boleto** que o devedor paga para cancelar, com o cedente sendo a própria
> serventia. Os dois são os boletos daqueles dois títulos.
>
> **Fica fora da fila.**

### CENPROT ▸

| | temos? | |
|---|---|---|
| Exportar arquivo XML | ⚠️ | a estrutura está medida (903 arquivos, 17.270 títulos); falta a **chave de 23 dígitos**, que **não vem por arquivo nenhum da CRA** — medido em 31/08 nos 125 arquivos de 2026 |
| **Arquivo de Emolumentos** | ❌ | **e aqui há caminho novo** — ver abaixo |
| Orçamento de Protesto | ❌ | |
| RESOLVE ▸ | ❌ | |

> **O ARQUIVO DE EMOLUMENTOS TEM SAÍDA, E ELA MUDOU HOJE.** Eu havia escrito
> que não existe exemplar dele nesta casa, e continua não existindo **em
> disco**. Mas o print mostra que **o E-Ofício sabe gerá-lo** — é um item de
> menu que funciona.
>
> **Basta o oficial gerar um arquivo pelo E-Ofício e guardá-lo.** Com um
> exemplar, o formato se mede numa tarde, como o quinto layout da desistência —
> que ficou pronto com **quatro** arquivos. O mesmo vale para o edital
> eletrônico e o orçamento de protesto.
>
> **Isto deixou de ser «não há como medir» e passou a ser «falta gerar».**

### Relatório ▸ — e dois deles são obrigação

| | temos? |
|---|---|
| Títulos Apontados | ❌ |
| Título por Ocorrência | ❌ |
| **Títulos com autorização de cancelamento via CRA** | ❌ — depende da AC |
| Títulos por Devedor | ⚠️ a lista de títulos busca por devedor; relatório impresso, não |
| Relação de certidões | ❌ |
| **Demonstrativo de Repasse ao Apresentante** | ❌ |
| **Títulos sem Ocorrência** | ❌ — é a lista do que está parado |
| **Títulos por Ocorrência — TJMA FISCALIZAÇÃO FERJ** | ❌ **obrigação com o Tribunal** |
| **Repasse dos Títulos Cancelados para TJMA** | ❌ **obrigação com o Tribunal** |

> **Os dois últimos não são conveniência: são prestação de contas ao TJMA**, e a
> serventia responde por eles. Merecem passada própria, com a norma na mão —
> nem o Código de Normas nem a tabela do FERJ foram lidos para este
> levantamento.

### Estatística ▸

Ocorrência de Título · Entrega da Intimação · **Títulos com AC** · **Gráfico de
Recebimento das AC** · Faixa do Protesto. **Nenhum existe.** Dois deles são
sobre a AC, que também não existe.

### Banco ▸ (Arquivo Remessa · Arquivo Retorno)

**E aqui há uma pergunta antes do trabalho.** O oficial corrigiu em 26/08/2026
que o arquivo do Banese que há no acervo de Sergipe é do **TJSE**, onde o
pagamento caía direto no banco — *aqui no TJMA o pagamento é na serventia*. Se
for assim, este menu **não se aplica**, e construí-lo seria trazer o fluxo de
outro estado. **É pergunta, e não trabalho.**

---

## O que este levantamento NÃO cobre

- **«Protocolar ▸» e «Pagar ▸»** não tiveram o submenu aberto nos prints; do
  primeiro nível não dá para saber o que trazem dentro.
- **Nenhum destes itens foi aberto na tela do E-Ofício.** Sei o **nome** de cada
  função, e não o que ela faz por dentro — quais campos pede, o que imprime,
  que arquivo gera. Para os que forem construídos, o print da tela vale mais que
  o do menu.
- **Não medi a frequência de uso.** Um item de menu existir não quer dizer que
  esta casa o use: o «Entregador de Intimações» é cadastro de terceirizado, e
  medido no acervo **as 1.618 entregas saíram pela mão da própria casa**.

---

## A RÉGUA DO OFICIAL, APLICADA AO MENU INTEIRO

> *«sobre tudo que o e-ofício faz, tente buscar dados dentro do banco de dados.
> Se não encontrar, possivelmente não é importante»* — 01/09/2026.

Ela desmontou metade deste levantamento em minutos, e me corrigiu duas vezes.
**Procura-se o DADO, e não o nome da tabela.**

### Não existe tabela nem coluna — logo, esta casa nunca fez

| item do menu | procurado |
|---|---|
| **Monitoramento de Devedor** ▸ | nenhuma tabela |
| **Exportação de Dados** ▸ (Serasa · Boa Vista · CNP Brasil) | nenhuma tabela |
| **Banco** ▸ (Arquivo Remessa · Arquivo Retorno) | nenhuma tabela |
| Registrar Ocorrência ▸ **Retificar** | nenhuma coluna |

O **Banco** já era suspeito por outro caminho: o oficial corrigiu em 26/08 que
o arquivo do Banese é do **TJSE**, onde o pagamento cai no banco — aqui é na
serventia. A ausência de tabela fecha a questão.

### A coluna existe e está ZERADA — logo, também não

| item | medido |
|---|---|
| **Repasse ao Apresentante** | `dtmRepasse_Data`: **0** de 1.370 |
| Taxa de edital | `curV_Edital`: **0** de 1.370 |
| Prescrito | `dtmPrescrito`: **0** de 1.370 |

> **Coluna zerada é mais forte que tabela ausente**: o E-Ofício tinha onde
> guardar e a casa nunca usou.

### Tem dado — e aqui o menu importa

| item | medido | temos? |
|---|---|---|
| **Motivo do protesto** (o texto do livro) | **1.132** | ✅ **01/09/2026** — `protesto_termo.py` |
| Edital publicado | **1.086** | ✅ |
| Protocolo de protesto | **435** | ✅ |
| Pagamentos | **341** | ✅ |
| **Taxa SDT** (distribuição, item 17.7) | **248** títulos, R$ 2.435 em 5 anos | ⚠️ **vive no boleto** — ver abaixo |
| Certidões emitidas | **65** | ✅ |
| Abertura de livro | **26** | ✅ pelo núcleo |
| Protesto gratuito | **6** | ⚠️ não medido a fundo |
| **Efeito suspensivo** | **1** | ✅ **01/09/2026** |
| Autorização de cancelamento (AC) | **2** | ❌ e não faz falta |

### A taxa SDT não é ato selado

`curV_SDT` está preenchida em **248 de 1.370** títulos — 18% —, com valores de
R$ 8,88 a R$ 10,67 e **R$ 2.435 em cinco anos**. É o item **17.7** da tabela
(*«Distribuição extrajudicial de títulos para protesto»*), e o sistema já o
conhece em `cx_servicos`.

**Mas ele não aparece em caminho de selo nenhum** — conferido nos 26.130 selos
medidos: `17.7` não está em nenhum dos seis caminhos do Protesto. Não é ato
selado: é **cobrança que entra no boleto**. E o boleto é o buraco já
documentado, com motivo medido — o verificador do código de barras não se
explicou (`AVISO_DE_INTIMACAO_MEDIDO.md`).

> E o item 17.7.2 da tabela liga uma coisa na outra: *«Não estão sujeitos à
> nova distribuição os títulos cujos protestos tenham sido **sustados por
> ordem judicial**»*.

### O `tbSDT` tem 1.394 linhas e NÃO é buraco

É a segunda maior tabela do Protesto, e por isso valia olhar. São as **linhas
da remessa recebida, campo a campo** — 80 colunas espelhando o arquivo de 600
posições, de **786 arquivos**.

**Nós já temos isso, e melhor**: `pt_remessas` guarda o arquivo **inteiro** com
`sha256`, e os títulos entram estruturados. O E-Ofício guardava os campos
crus; nós guardamos a fonte e o resultado.

---

## O que eu proporia olhar primeiro, se a decisão fosse minha

Não é — mas a ordem que os fatos sugerem:

1. ~~**A AC (Autorização de Cancelamento) da CRA.**~~ — **medida e descartada
   em 01/09/2026**: 2 títulos em 1.370, e o cancelamento chega direto ao
   balcão. Não há exemplar do arquivo em nenhuma das duas pastas (695
   conferidos), e como é arquivo que a Central *manda*, nem se pode gerar um.
2. ~~**O efeito suspensivo.**~~ — **feito em 01/09/2026**, e foi o primeiro.
3. ~~**O motivo do protesto**~~ — **feito em 01/09/2026**, e era o maior:
   1.132 linhas, e o Livro de Registro de Protestos saía sem texto.
4. **O arquivo de emolumentos e o edital eletrônico do CENPROT** — assim que o
   oficial gerar um exemplar de cada pelo E-Ofício.
5. **Os dois relatórios do TJMA**, com a norma lida antes.
6. **A intimação digital (Resolve)**, que é a que mais mudaria o dia — e é a que
   mais depende de decisão, porque é contrato com terceiro.

**E o que a régua tirou da fila**: monitoramento de devedor, exportação para os
birôs, arquivo de banco, retificação, repasse ao apresentante — **nenhum tem
uma linha de dado nesta casa**.

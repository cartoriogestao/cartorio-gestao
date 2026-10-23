# O carimbo das certidões — 17/09/2026

> «preciso que o carimbo das certidoes (todas) saia com data e hora da emissao,
> emolumentos, qr code, link de acesso ao tj, requerente. precisamos de um
> carimbo com todas informacoes que usamos para emitir o selo. bole um modelo e
> me mostra aqui pra eu aprovar»
>
> — o oficial, 17/09/2026. O modelo foi apresentado com as medições ao lado e
> ele respondeu **«pode fazer»** e **«tudo conforme pontuado»**, o que respondeu
> também as três perguntas que foram junto.

## O modelo aprovado

```
┌────────┬──────────────────────────────────────────────────────────────────────────┐
│        │ SELO DA CERTIDÃO                                                         │
│   ▓▓   │ CERINT0000009ZYQS3MCYZOV5U97                                             │
│  ▓QR▓  │ Ato 16.24.4 · emitida em 17/09/2026 às 16:30:36                          │
│   ▓▓   │ Requerente: PESSOA EXEMPLO                           │
│ 1,45cm │ Total R$ 101,88 Emol R$ 90,96 FERC R$ 2,73 FEMP R$ 3,64 FADEP R$ 3,64    │
│        │ FERRFIS R$ 0,91 · Selo Isento                                            │
│        │ Confira em https://selo.tjma.jus.br/?selo=CERINT0000009ZYQS3MCYZOV5U97   │
└────────┴──────────────────────────────────────────────────────────────────────────┘
```

**TUDO SAI DO QUE O SELO DECLARA.** Nada é remontado pelo sistema: se o
aparelho não declarar um campo, a linha não sai — em vez de sair uma conta
parecida, feita depois, num papel que a serventia assina.

## As três decisões dele, e o que cada uma mudou

### 1. O molde do RCPN ficou alinhado

As três certidões do civil (nascimento, casamento, óbito) imprimem o selo por
um quadro que está **dentro do `.odt` que ele desenha no LibreOffice**, com
marcadores `@`. Ele já trazia quase tudo — o número, o detalhe, a linha de
valores, o QR e o endereço. Faltavam duas coisas, e as duas são as que ele
pediu:

| | antes | agora |
|---|---|---|
| requerente | dentro do `@selo1_detalhe`, sem rótulo, emendado com o ato e a data | **linha própria**: `Requerente: FULANO` |
| o endereço | `https://selo.tjma.jus.br` — o portal, fixo no desenho | `…/?selo=<código>`, **que abre este selo** |
| as marcas | não saíam | na linha de valores, ao lado do número que elas qualificam |

**O que mudou no desenho dele foi o mínimo:** uma linha a mais em cada uma das
duas caixas, e o hiperlink virou marcador. Nada de geometria, nada de estilo,
nada de cor. O `.bak_pre_carimbo_completo` fica ao lado dos três.

**`@seloN_detalhe` continua no vocabulário**, e continua sendo o que era. O
molde deixou de usá-lo; se ele o repuser amanhã, imprime o que sempre imprimiu
— em vez de sair `@selo1_detalhe` escrito numa certidão assinada.

### 2. «Requerente» é fiel, e foi medido

O selo chama o campo de `Parte(s)`. Medido nos **691** selos de certidão desta
casa: **687 trazem o campo, e em todos vem nome de pessoa** — nenhum traz o
número da matrícula, que é o que o sistema manda quando não há requerente
(`{'nome': 'MATRICULA 1116'}`).

### 3. As marcas do selo passaram a sair

Medido no razão inteiro — **25.839 selos com texto** —, o que o aparelho
escreve entre o último valor e o «Consulte em» é sempre uma destas coisas:

| | |
|---|---|
| nada | **25.607** |
| `Selo Isento` | **168** |
| `Diferido` | **49** |
| `Diferido, Selo Isento` | **4** |
| (o link, na forma de 2020) | **11** |

**E ELAS NÃO SE DEDUZEM DO VALOR.** O selo isento desta casa vem com os
emolumentos escritos — `Total R$ 115,44 Emol R$ 104,00 … Selo Isento` —, de
modo que um carimbo que imprima só os valores **afirma que se cobrou**. A marca
é justamente o que desmente o número ao lado dela, e por isso ela anda colada
nele, e não numa linha própria.

## O que a medição decidiu: a largura

O carimbo de **meia largura** foi desenhado em 15/09 para o **ato da ficha**,
por ordem dele — «deixando o outro lado para o segundo selo» —, porque **o ato
pode ter dois**. A certidão não: são **691 selos de certidão e um por
certidão**.

Medido a 5,5 pt, que é o corpo do carimbo, contra a coluna de texto de 6,25 cm:

| a linha | largura | cabia? |
|---|---|---|
| número do selo | 3,44 cm | sim |
| `Ato 16.24.4 · emitida em 17/09/2026 às 16:30:36` | 4,23 cm | sim |
| `Requerente: PESSOA EXEMPLO` | 5,10 cm | sim |
| **a linha dos valores, com a marca** | **9,61 cm** | **não — quebrava** |
| **o link com `?selo=`** | **6,97 cm** | **não — quebrava** |

E a mais larga das **691 certidões reais** mede **9,33 cm** — um requerente que
é um sindicato, com o nome inteiro. **Na largura cheia (14,25 cm ao lado do QR)
todas cabem numa linha só.**

**O ato da ficha não mudou**, e há teste que o guarda: ele continua com dois por
fileira, sem a linha do requerente, com `Ato: 16.24.4 · 17/09/2026 16:30:36`. No
livro, o carimbo está ao lado do próprio ato, que já nomeia as partes duas
linhas acima — repetir ali gasta a linha que o livro não tem.

## Duas certidões não tinham carimbo nenhum

| certidão | emitidas | selos no razão | carimbo antes | agora |
|---|---|---|---|---|
| Registro de Imóveis | 375 | 670 | meia largura, sem requerente | o completo |
| RI — por reprodução da digitalização | — | — | o do ato | o completo |
| RCPN — inteiro teor | — | — | o do ato | o completo |
| RCPN — nascimento, casamento, óbito | 55 | — | o molde `.odt` dele | alinhado |
| **Protesto** | 0 lavradas aqui | **57** | **nenhum** | o completo |
| **RCPJ / RTD / Livro 3** | 2 | **38** | **nenhum** | o completo |

As duas últimas montavam o `.odt` do teor e paravam ali —
`gerar_odt(html_para_odf(html))`. **O selo era comprado, gravado no razão e não
aparecia no papel.** Selo comprado que não sai impresso é o inverso do carimbo
sem valores: os dois fazem a certidão afirmar menos do que o selo diz.

## O que o conserto achou pelo caminho

**O LINK SUMIA EM ONZE SELOS, TRÊS DELES CERTIDÕES.** Até maio de 2020 o
aparelho escrevia «Consulte **a validade deste selo** em https://…»; de lá para
cá escreve «Consulte em https://…». O leitor procurava a segunda forma, literal,
e nos onze devolvia vazio — **o papel saía sem o endereço de consulta**, que é
uma das coisas que ele mandou pôr no carimbo. São 8 reconhecimentos de firma e
**3 certidões do Registro de Imóveis**, de 20/05/2020. Não é caso raro que se
despreza: é o caso que aparece quando alguém pede a segunda via de uma certidão
de 2020.

Conferido depois do conserto: **os 25.839 selos com texto devolvem o endereço**,
contra 25.828 antes.

**E HAVIA TRÊS CÓPIAS DO AJUDANTE DO QR** — em `ri_web`, em `rc_certidao_odt` e
em `rc_certidao_inteiro_teor` —, e as certidões novas fariam a quarta e a
quinta. O que vai **dentro** do QR de um papel assinado não pode ter cinco
versões. Ficou uma: `ri_odt.png_do_qr_do_selo`.

## Onde cada coisa mora agora

| | |
|---|---|
| `selo.ler_texto` | lê o texto do aparelho — e passou a ler as **marcas** e o link nas duas formas |
| `selo_no_papel` | **o que o carimbo diz**: `ato_e_data`, `requerente`, `valores_com_marcas`, `link_de_consulta`, `linhas_do_carimbo` |
| `ri_odt.partes_do_carimbo` | o mesmo conteúdo, para quem desenha em ODF — com `feitio` de ato ou de certidão |
| `ri_odt.carimbo_da_certidao_odf` | **o carimbo pronto** da certidão: um QR por selo, as imagens do pacote, a largura inteira |
| `ato_selado.etiqueta_do_ato` | **onde está a etiqueta**: `tabela` + `ato_id` no razão, com o número gravado no ato como segunda porta |
| `rc_certidao_odt.valores` | o vocabulário `@` do molde do RCPN — pedindo as mesmas linhas |

**A CHAVE DA ETIQUETA É `tabela` MAIS `ato_id`, E HÁ UMA SEGUNDA PORTA.** Por
`ato_id` sozinho vêm selos de outra atribuição (medido em 15/09 — três
reconhecimentos de firma de 2022 responderam por ids de `ri_atos`). A segunda
porta, pelo **número** gravado no ato, existe porque **762 dos 765** selos de
certidão do razão estão com `tabela` nula: vieram da carga do acervo, que gravou
o selo dentro do ato sem amarrar o razão. Sem ela, toda certidão anterior a este
sistema sairia sem valores.

**E O NÚMERO CONTINUA VALENDO QUANDO O RAZÃO NÃO TEM NADA**: o carimbo sai com o
número e sem a linha de valores — que é a verdade. Remontar a conta ali seria
imprimir num papel assinado um valor que o selo não declara.

## Cada linha do carimbo tem nome, e isso não é estilo

O carimbo em ODF recebe a lista pronta e a desenha de cima para baixo; **o molde
`.odt` do RCPN não pode** — ele tem um marcador por linha, no lugar que o
oficial desenhou. Pedir a lista e pegar `linhas[1]` faria o papel dele depender
da **ordem** de uma lista de outro módulo: no dia em que o carimbo ganhasse uma
linha, a certidão sairia com o requerente no lugar do ato, **sem erro em lugar
nenhum**.

## Um erro meu desta passada, e ele está registrado

Ao caçar uma vermelha antiga, eu condicionei a **fronteira do acervo** («números
menores que 4.015 são acervo») à existência de acervo na casa. A razão parecia
boa — numa instalação nova as matrículas começam em 1, e sem a condição toda
ficha nasce «de acervo». **Mas a fronteira não é guarda de programador: é ordem
dele, de hoje**, e `tests/test_ri_regra_acervo_4015.py` a declara na primeira
linha. **Voltou inteira no mesmo dia.**

O que ficou no lugar: **as bancadas passaram a abrir matrícula no intervalo do
sistema**, que é o que a produção faz — elas abriam a matrícula **1** e a
**4011**, números que esta casa não produz (o próximo é 4019). Dez testes
morriam por isso, e **nenhum deles fala de acervo**: falam de expurgo, de parte
sem papel, de renumeração, de certidão.

**E FICA DECLARADO O QUE A FRONTEIRA PRODUZ NUMA INSTALAÇÃO NOVA**, que é
pergunta para ele e não conserto meu: o primeiro número é 1, a ficha nasce
`ACERVO` e sem quem a abriu, e o primeiro ato é recusado pedindo «o número do
ato conforme o livro físico» de um livro que não existe. **Nesta casa não
acontece.**

## O que NÃO é desta passada, e está medido

Rodando a fatia contra o **pacote 3.6.139, como ele está instalado**, e com os
testes de hoje:

| | |
|---|---|
| `tests/test_atribuicoes_web.py` | **11 vermelhas** |
| `tests/test_habilitacao_web.py` | **8 vermelhas** |
| `tests/test_desfazer_averbacoes_rcpj.py` | **4 vermelhas** |

As 23 falham **igual** no pacote instalado e na árvore de hoje — não são desta
passada. E são todas a mesma família, que já estava declarada: **o registro, o
assento e a averbação que não conseguem selo são CANCELADOS**, e «não ter item
de cobrança marcado» conta como não conseguir selo. Uma delas se chama, com
todas as letras, `test_a_habilitacao_continua_expedida_sem_o_selador`.

**É a segunda metade do item 1 que falta nesses módulos.** A regra que ele
decidiu em 16/09 tem duas partes, e o RI cumpre as duas: *o que só o selo diz*
— aparelho fora do ar, credencial vencida, recusa do TJMA — **suspende**, porque
corrigir e lavrar de novo resolve; *o que falta preencher* **não suspende**, e o
ato fica lavrado com o aviso. No RCPJ/RTD, no RCPN e no Protesto só a primeira
metade está ligada.

**Não consertei**, e por duas razões: o módulo é da outra passada (a regra da
casa é «quem não está construindo o módulo não mexe nele», e em 02/09 consertar
por cima me custou ser sobrescrito em cinco minutos), e a decisão de o registro
sem item de cobrança poder ou não ser lavrado **é dele**.

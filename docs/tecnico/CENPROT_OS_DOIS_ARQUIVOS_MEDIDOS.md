# Os dois arquivos do CENPROT, medidos — e a chave que se explicou

Medido em **01/09/2026**, nos dois arquivos que o oficial gerou pelo E-Ofício e
guardou. São **desta casa** — `MA-2198765-01` é Maranhão / Cidade Exemplo /
cartório 01.

| arquivo | o que é | tamanho |
|---|---|---|
| `MA-2198765-01-E-20260831-01.txt` | **o arquivo de emolumentos** | 173 linhas |
| `MA-2198765-01-P-20260831-01.xml` | o XML de protestados, **versão 1.23-geral** | 175 títulos |

> **Isto mudou de «não há como medir» para «medido» com um gesto do oficial.**
> Em 31/08 eu havia escrito que não existia um único exemplar do arquivo de
> emolumentos em lugar nenhum da casa — e continuava não existindo **em
> disco**. O print do menu mostrou que o E-Ofício sabe gerá-lo; bastou gerar.

---

## 1. O arquivo de emolumentos — o mais simples de todos

**Separado por `|`, com linha de cabeçalho.** Nada de posições fixas.

```
nm_chave|vl_retirada|vl_cancelamento|cd_ibge|nr_cartorio|dt_movimento
21987650121105501251113|138.96|319.54|2198765|01|20260831
21987650131146601260105|166.89|365.54|2198765|01|20260831
```

| campo | o que é | medido |
|---|---|---|
| `nm_chave` | a chave única do CENPROT, 23 dígitos | 173 de 173 |
| `vl_retirada` | o que o devedor paga para **retirar** | 25 valores distintos |
| `vl_cancelamento` | o que ele paga para **cancelar** | 26 valores distintos |
| `cd_ibge` | `2198765` | constante |
| `nr_cartorio` | `01` | constante |
| `dt_movimento` | `20260831`, AAAAMMDD | constante no arquivo |

Os dois andam **em par** — R$ 100,73 → R$ 255,60 em 57 linhas; R$ 138,96 →
R$ 319,54 em 28 — e sobem com o valor do título. **Mas o valor do título não
os determina**, e é isso que impede gerar o arquivo hoje.

> **EU ESCREVI AQUI QUE «OS VALORES SAEM DA FAIXA DO TÍTULO», E A MEDIÇÃO
> SEGUINTE ME DESMENTIU.** Cruzando os 173 pelo `id` — **173 de 173 casam** —,
> títulos de valor quase igual pagam preços diferentes:
>
> ```
> R$ 200,95  ->  retirada  96,54       R$ 207,71  ->  retirada  89,79
> R$ 205,76  ->  retirada 100,73       R$ 226,27  ->  retirada  93,98
> ```
>
> São **quatro preços** na mesma faixa de valor, separados por incrementos
> fixos de **R$ 4,19 e R$ 6,75**. A faixa dá a base; alguma coisa por título
> soma esses pedaços.

**E as duas explicações óbvias foram testadas e refutadas**, nos 43 títulos
entre R$ 200 e R$ 340:

| hipótese | o que a medição diz |
|---|---|
| é a **intimação** (edital ou pessoal) | **não**: os 5 títulos de R$ 96,54 e os 36 de R$ 100,73 têm as bandeiras `intimado`, `edital` e `ocorrencia` **idênticas** |
| é a **tabela do ano** do apontamento | **não**: abril de 2026 aparece em **três** grupos de preço diferentes |

**O que falta não está no XML.** Ele traz o valor, os devedores, a ocorrência e
o livro; não traz **o que foi efetivamente cobrado daquele título** — quais
itens entraram. O E-Ofício sabe porque tem o lançamento; este arquivo carrega
só o resultado.

**Os itens desta casa resolvem, e o total já inclui os fundos** — o que não
resolve é a composição:

```
17.10.1  R$ 26,25     17.2  R$ 10,68     17.3  R$ 34,88     17.5.1  R$ 53,58
17.4  por faixa — 17.4.2 (R$ 68,03 a 220,07) = R$ 13,90
```

Para um título de R$ 89,42 isso dá **R$ 50,83** de retirada, e o arquivo diz
**R$ 96,54**. **Faltam R$ 45,71 que não sei de onde vêm, e por isso não escrevo
o arquivo** — número inventado num arquivo que vai à Central é pior que arquivo
nenhum.

---

## 1-B. E OS VALORES SE EXPLICARAM — com o arquivo do ano e o print do orçamento

**Medido em 01/09/2026**, depois de o oficial baixar o arquivo de emolumentos do
**ano de 2025 inteiro** (375 títulos, dez/24 a dez/25) e um print da tela
*Orçamento — custas e serviços* do E-Ofício.

### A fórmula

```
retirada     = 17.7 + 17.2 + 17.10.1 + 17.9 x N   +  FAIXA 17.4 (pelo valor)
cancelamento = os mesmos + 17.3 + 17.5.1 x 2      +  FAIXA 17.1 (pelo valor)
```

E os dois itens de faixa **são o que a norma diz que são**:

| | |
|---|---|
| **17.4** | «quando, após o apontamento e antes ou depois da intimação, ocorrer a **liquidação do título ou a desistência**» — é a **retirada** |
| **17.1** | «**protesto** de título de crédito (sobre o valor do título)» — é o que se **cancela** |

### Como isso se provou

**Contra o arquivo do ano: 166 de 173** títulos que deu para casar com o acervo
batem **no centavo**, retirada e cancelamento. (Os outros 202 do arquivo caem em
dias com mais de um título, onde o par não é certo.)

E as fronteiras das faixas batem no centavo: R$ 220,00 cai na 17.4.2
(68,03–220,07) e R$ 233,25 na 17.4.3 (220,08–413,47), com os preços mudando
exatamente ali.

**O print do orçamento confirmou a mecânica dos itens**, um a um — cada linha
dele é `VALOR + FERC + FADEP + FEMP + FERRFIS`, e a soma é o `total` da nossa
`cx_servico_valores`:

| item | o print | a nossa tabela |
|---|---|---|
| 17.7 | 10,67+0,32+0,43+0,43+0,11 | **11,96** |
| 17.2 | 9,53+0,29+0,38+0,38+0,10 | **10,68** |
| 17.1.5 | 84,69+2,54+3,39+3,39+0,85 | **94,86** |
| 17.9 | 6,03+0,18+0,24+0,24+0,06 | **6,75** |
| 17.5.1 | 47,84+1,44+1,91+1,91+0,48 | **53,58** |
| 17.10.1 | 23,44+0,70+0,94+0,94+0,23 | **26,25** |

Somados, **R$ 217,58** — o total que o print mostra. **É o ISS que não entra**,
e é a regra que este projeto já tinha medida: `custas.CAMPOS_NO_TOTAL`.

### AS CONSTANTES NÃO SE DECOMPÕEM, e eu disse que sim

Escrevi aqui, no mesmo dia, que cada constante fechava de **um jeito só** e
chamei isso de determinação. **Era numerologia com cara de medição**: a
unicidade veio de eu ter escolhido os seis itens da busca. Com **todos** os
itens fixos do grupo 17 (18 deles, quantidades de 0 a 5):

| constante | combinações que fecham |
|---|---|
| 82,64 (retirada) | **9** |
| 224,68 (cancelamento) | **42** |

**Somar itens de tabela até dar o número é o que sempre fecha** — é a mesma
armadilha da busca exaustiva que já falhou no verificador do boleto e no da
matrícula de 32 dígitos, e ali eu soube parar. Aqui não soube, porque desta vez
o resultado era bonito.

**E QUEM ME DESMENTIU FOI A COLUNA QUE O OFICIAL MANDOU PROCURAR.**

### O QUE EU TINHA ERRADO, E O QUE ERA

Eu havia escrito que **«os valores não se reproduzem»** e que faltavam
**R$ 45,71** por título sem explicação. Errado nas duas metades:

- **a faixa era outra.** Eu somava a faixa do **17.4** ao que devia levar a do
  **17.1**, e comparava com o total errado;
- **o componente variável é o número de FOLHAS.** O `17.9` é «arquivamento,
  **por folha** do documento», e custa **R$ 6,75** — que é exatamente o
  incremento de 6,75 que eu media entre títulos da mesma faixa e não sabia de
  onde vinha. O print mostra `17.9` com **quantidade 3**; os títulos do arquivo
  do ano têm **5**.

**Duas medições desmentiram uma conclusão que eu tinha dado por fechada** — e
nenhuma das duas foi releitura: foram um arquivo maior e um print, os dois
trazidos pelo oficial. **O que fecha lacuna de layout é mais amostra**, pela
quinta vez neste projeto.

### A COLUNA EXISTE — `curArquivamento_Valor`

Procurada a pedido do oficial, e achada **pela forma do dado e não pelo nome**:
eu procurava uma *contagem* de folhas, e a casa guarda o *valor*.

`tbAvisoProtesto.curArquivamento_Valor` está preenchida em **1.370 de 1.370** —
zero em 1.175, com valor em 195 —, e ao lado dela ficam os quatro fundos em
colunas próprias (`_Ferc`, `_MP`, `_DP`, `_ferrfis`). Há a irmã do
cancelamento, `curCancelamento_Arquivamento_Valor`.

**Ela decodifica exato**, e por duas fontes que se conferem: o valor dividido
pelo **emolumento do item 17.9 daquele ano** dá sempre 3, 4 ou 5 folhas.

| valor na coluna | ÷ emolumento do ano | folhas |
|---|---|---|
| 15,06 · 20,08 | 5,02 (vigência 10018) | 3 · 4 |
| 15,93 · 21,24 | 5,31 (10019) | 3 · 4 |
| 16,56 · 22,08 | 5,52 (10020) | 3 · 4 |
| 17,37 · 23,16 | 5,79 (10021) | 3 · 4 |
| 18,09 · 24,12 · 30,15 | 6,03 (10022) | 3 · 4 · 5 |

Os cinco divisores são exatamente os cinco últimos preços do 17.9 na tabela —
e eu os derivei do acervo **antes** de olhar a tabela.

### E ELA DESMENTE A DECOMPOSIÇÃO: é ZERO nos 167 títulos que casei

Todos os títulos cujo preço eu consegui casar têm `curArquivamento_Valor = 0`,
e o preço deles carrega a constante inteira. **Logo a constante não é
arquivamento**, e o «17.9 x5» que escrevi acima era uma das nove somas
possíveis, escolhida por eu ter limitado a busca.

### MAS ISSO NÃO IMPEDE GERAR O ARQUIVO — e essa é a boa notícia

**A constante é constante, e é isso que está medido**: 166 de 173 títulos do
ano batem no centavo com **um único par** de constantes. O gerador precisa da
constante, e não da receita dela.

```
retirada     = 82,64  + faixa 17.4 (pelo valor do título)
cancelamento = 224,68 + faixa 17.1 (pelo valor do título)
```

**O que fica em aberto é de outra natureza, e é honesto declarar:** não se sabe
de que itens a constante é feita, e por isso **ela não acompanha sozinha uma
tabela nova**. Quando o TJMA publicar a próxima, os dois números precisam ser
medidos de novo — com um arquivo de emolumentos gerado depois da virada. Está
declarado no módulo, e é o tipo de coisa que a correição pergunta.

---

## 1-C. E O ARQUIVO DE EDITAL FECHOU A DECOMPOSIÇÃO — nomeando os itens

O oficial salvou dois arquivos de edital em 01/09/2026, e o segundo,
`E140826.XML`, traz por título um bloco `<custas>` com **um `<encargo>` por
item, com o nome por extenso**:

```xml
<encargo><nome>Distribuição extrajudicial de títulos…</nome><valor>11.85</valor>
<encargo><nome>Intimação ou edital por título…</nome><valor>10.58</valor>
<encargo><nome>Quando, após o apontamento (…) liquidação…</nome><valor>17.93</valor>
<encargo><nome>Arquivamento, por folha do documento</nome><valor>26.76</valor>
<encargo><nome>Diligência para entrega de intimação</nome><valor>26.02</valor>
```

**Não é busca combinatória: é o E-Ofício dizendo o que cobrou.** E confirma
exatamente a receita que eu havia proposto e depois retirado.

### Duas coisas que só este arquivo mostrava

**O EDITAL ESCREVE OS ITENS SEM O FERRFIS.** `11,85 = 11,96 − 0,11`;
`17,93 = 18,09 − 0,16`. O arquivo de emolumentos, esse, leva o total inteiro —
com os quatro fundos. Reconstruído item a item, o edital bate em **6 de 6**
títulos, no centavo.

**E O `17.9` É POR FOLHA, com quantidade que varia**: `26,76 = 4 × 6,69`. Os
títulos do edital têm **quatro** folhas; os do arquivo de emolumentos do ano
têm **cinco** (166 de 173). Não é contradição — é o que a norma diz que o item
é: «arquivamento, **por folha** do documento».

### O que isso mudou no sistema

A constante **deixou de ser um número escrito** e passou a ser **somada da
tabela** (`protesto_cenprot.constantes`). Consequência prática: o arquivo
**acompanha a virada da tabela sozinho**. Antes o módulo recusava gerar em
qualquer vigência que não a 10022 — precaução necessária enquanto a receita era
desconhecida, e desnecessária agora.

**E as duas fontes ficaram amarradas por um teste**: a soma dos itens tem de
dar exatamente os R$ 82,64 e R$ 224,68 medidos no arquivo do ano. Se um dia
divergirem — item que mudou de código, tabela importada pela metade —, o
vermelho aparece no teste e não num arquivo publicado na Central.

### A LIÇÃO, e ela é sobre a minha própria correção

**Foi a terceira vez neste mesmo dia que mais dado mudou a conclusão, e a
segunda em que a correção que eu fiz era pior que o original.**

| o que eu disse | o que era |
|---|---|
| «os valores não se reproduzem, faltam R$ 45,71» | a faixa era outra (17.1, não 17.4) |
| «a decomposição tem solução única» | verdade a receita, **falso o argumento** — 9 somas dão 82,64 |
| «logo é numerologia, e a constante não se explica» | **o edital nomeia os itens**, e a receita era a certa |

O erro do meio foi legítimo: com nove combinações possíveis, eu não tinha como
escolher. **O erro foi concluir que não havia como saber, em vez de pedir outro
arquivo.** Quando a dúvida for entre «medi errado» e «não há como saber», o
caminho é o mesmo que resolveu esta quatro vezes seguidas: **mais amostra.**

---

## 2. A chave de 23 dígitos SE EXPLICOU — e não era o verificador

Este projeto tentou explicá-la duas vezes e chamou o resultado de
«verificador que não se explica». **Ela não tem verificador: tem data.**

```
2198765   01412433     01    260417
IBGE(7)   CENPROT(8) cart(2) AAMMDD(6)
```

| parte | conferido |
|---|---|
| os 6 últimos são a **data do protocolo** (AAMMDD) | **175 de 175** |
| as posições 16–17 são o número do cartório | 175 de 175, **e 2.376 em Sergipe** |
| os 7 primeiros são o IBGE da comarca | 175 de 175, **e 2.376 em Sergipe** |

O que fecha a leitura são **duas fontes dentro do mesmo arquivo**: a chave
`21987650141243301260417` termina em `260417`, e o mesmo título traz
`<data_protocolo>2026-04-17</data_protocolo>`. Em 175 de 175.

> **E EU ABRI O MEIO ERRADO NA PRIMEIRA VERSÃO DESTE DOCUMENTO.** Escrevi que
> as posições 8–9 são o cartório e que sobravam seis dígitos de sequencial,
> porque aqui aquelas duas são `01` em 175 de 175. **Não são o cartório**: o
> `CENPROT_XML_MEDIDO.md` deste projeto mediu 2.376 chaves de **outra
> serventia** e registra `2801405|0005640|2|01|200330`, com **`00`** ali.
>
> **Regularidade forte dentro de uma casa parece lei até alguém olhar outra
> casa** — a lição da posição 566, e desta vez a outra casa já estava medida na
> nossa própria documentação. Bastava abrir o documento vizinho.

**O bloco 8–15 fica inteiro: oito dígitos da Central.** A leitura de Sergipe os
separa em protocolo(7) + verificador(1); **aqui essa separação não se confirma**
— o nosso protocolo é `2604170001` e o bloco é `01412433`. O que se vê é que ele
sobe com o tempo (`01211055` nov/25 < `01311466` jan/26 < `01412433` abr/26), e
**não se compõe aqui**.

---

## 3. E NÃO PRECISA COMPOR — o XML devolve a chave ao lado do nosso protocolo

Cada `<titulo>` do XML traz o `id` (a chave) **e** o `<protocolo>` que é o
nosso. Em **175 de 175**.

Isso resolve a pergunta que o oficial respondeu em 26/08/2026 — *«serventia não
gera chave única»* — pelo lado prático: **ela não gera, e não precisa**. A
Central devolve, e o sistema guarda. `pt_titulos.chave_cenprot` existe desde o
começo e está vazia nos 1.366; agora há de onde preenchê-la.

> E os dois arquivos falam dos mesmos títulos: **173 das 173 chaves do arquivo
> de emolumentos estão no XML.**

### O que mais o XML entrega, e que vale ter

```xml
<titulo id="21987650141243301260417">
  <cedente>…</cedente>   <sacador>…</sacador>
  <nosso_numero>YK0000000000072</nosso_numero>
  <especie>DMI</especie>            <numero_titulo>EXEMPLO0003</numero_titulo>
  <data_emissao>2026-01-29</data_emissao>
  <data_vencimento>2026-04-05</data_vencimento>
  <valor>2007.8500</valor>          <saldo>2007.8500</saldo>
  <devedores total="1">
    <devedor sequencia="1">
      <nome>…</nome> <CPF>…</CPF>
      <intimado>false</intimado>
      <edital>false</edital>  <edital_motivo />
    </devedor>
  </devedores>
  <protocolo>2604170001</protocolo>  <data_protocolo>2026-04-17</data_protocolo>
  <ocorrencia>2</ocorrencia>         <data_ocorrencia>2026-04-23</data_ocorrencia>
  <tipo_protesto>C</tipo_protesto>   <motivo_protesto>1</motivo_protesto>
  <tipo_livro>G</tipo_livro> <num_livro>9</num_livro> <num_folha>70</num_folha>
  <acervo_herdado>false</acervo_herdado>
  <anuencia><flag>false</flag></anuencia>
</titulo>
```

**E ele é a versão `1.23-geral`** — o contrato que este sistema carrega é o
`1.22`. Os XSDs de `C:\ARPNET\CRA\Remessa` são de 2017; **a 1.23 não está na
casa.**

---

## O que dá para construir agora, e em que ordem

1. ~~**O importador do XML**~~ — **feito em 01/09/2026**:
   `protesto_cenprot.py`, com tela em *Protesto → O dia da CRA → Chave do
   CENPROT*. 49 testes, dois deles ensaios contra o arquivo real.

   **Ele ainda não tem o que casar na produção**, e a tela diz isso com três
   números em vez de um: `protocolo` está vazio em 1.366 de 1.366 porque **a
   passada da carga que o traz ainda não rodou no servidor**. Contra a produção
   de hoje o `conferir` devolve 175 fora — e está certo.

   **Três guardas antes de gravar**, e o terceiro nasceu ao construir a tela:

   | guarda | o que ele impede |
   |---|---|
   | o arquivo é **desta serventia**? (comarca e cartório do cabeçalho) | o arquivo da casa vizinha escrever aqui as chaves dos títulos dela — nem o protocolo nem o nosso número são nacionais |
   | protocolo **e** nosso número (ou o valor) | escrever no título de A a chave do título de B |
   | chave que já está lá **não se sobrescreve** | os dois lados passarem a falar de títulos diferentes com o mesmo nome |
2. **O escritor do arquivo de emolumentos NÃO se constrói hoje**, e não é
   preguiça: o **formato** está medido inteiro, e os **valores** não se
   reproduzem — faltam R$ 45,71 por título que não estão em lugar nenhum dos
   dois arquivos. O que fecharia isto é o **lançamento** de um título retirado
   e de um cancelado: com os itens que a casa cobrou de verdade em cada um, a
   composição se lê numa tarde.
3. **Conferir a 1.23 contra a 1.22** antes de gerar XML — três campos que eu vi
   e que não sei se existem na 1.22: `tipo_endosso`, `acervo_herdado` e
   `anuencia`.

## O que continua sem exemplar

O **edital eletrônico** e o **orçamento de protesto**, os outros dois itens do
menu CENPROT. Mesmo caminho: um arquivo de cada, gerado pelo E-Ofício.

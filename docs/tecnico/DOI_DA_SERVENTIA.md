# A DOI da serventia — um arquivo só, das duas atribuições

**28/08/2026.** O que o oficial relatou pela janela da ajuda, em 27/08:

> «Consta apenas DOI e CTP no registro de imóveis, deveríamos ter para as escrituras
> também, com intercomunicabilidade para que o arquivo da DOI seja possível gerar
> único, com tudo da serventia.»

E a decisão dele em 28/08, quando perguntei como preferia: **«Os dois: campo na ficha e
conferência depois»** e **«Um arquivo só, das duas atribuições»**.

---

## O que se mediu antes de construir

**As colunas já existiam, e nenhuma tela as preenchia.** `nt_atos` tem `com_imovel`,
`doi_transacao`, `doi_tipo_imovel`, `doi_matricula`, `doi_endereco` e `doi_area` desde a
importação do E-Ofício. Medido no banco de produção: **zero das 47 escrituras** tem
`com_imovel = 1`.

**E `notas_doi.py` — que tem o módulo inteiro** (prazo, conferência, montagem, geração do
arquivo, e o nome do tabelionato na fachada) — **era chamado só pelo Registro de
Imóveis.**

Não faltava o módulo nem o lugar de guardar. Faltava a tela, e faltava juntar as pontas.

**Por que um arquivo e não dois:** é o que a Receita espera — uma declaração por serventia
por mês —, e esta casa tem um CNS só, de ofício único. Duas telas gerariam dois arquivos e
alguém mandaria um só. O prazo é do mês, e quem controla o prazo tem de ver o mês inteiro
num lugar.

---

## Quem alienou e quem adquiriu — a medição que mudou o desenho

Eu havia escrito a separação lendo uma coluna `papel` de `nt_ato_partes`. **Essa coluna não
existe**: a tabela guarda `qualificacao`. O código não teria separado ninguém — as duas
listas sairiam vazias, e a declaração iria à Receita sem alienante nem adquirente.

Medido nas **88 partes das 47 escrituras** desta casa:

| Vezes | Escrito no acervo | Lado |
|---:|---|---|
| 15 | `VENDEDOR(A)` | aliena |
| 15 | `COMPRADOR(A)` | adquire |
| 10 | `CEDENTE(S)` | aliena |
| 8 | `VENDEDORA` | aliena |
| 6 | `PROPRIETÁRIO(A)` / `Proprietário(a)` | **dúvida** |
| 4 | `Vendedor(a)` | aliena |
| 4 | `OUTORGADO` | adquire |
| 4 | `Comprador(a)` | adquire |
| 3 | `COMPRADORA` | adquire |
| 3 | `OUTORGANTE` / `Outorgante` | aliena |
| 9 | `PROCURADOR...` (seis grafias) | **fora do negócio** |
| 2 | `DECLARANTE` | **dúvida** |
| 1 | `HERDEIRO(A) CEDENTE` | aliena |
| 1 | `DONATÁRIO(A)` | adquire |
| 1 | `TESTEMUNHA` | fora |
| 1 | `REPRESENTANTE` | fora |

**A qualificação é campo livre**, e o balcão escreve como fala. Não há catálogo a
consultar — há o que está escrito.

### A armadilha, que estava a um passo

**`PROCURADOR DO VENDEDOR` contém `VENDEDOR`.** Quem procurar o vendedor primeiro declara
à Receita que o procurador vendeu o imóvel — o CPF de quem só assinou por outro, numa
transação que ele não fez, cruzado com a declaração de imposto de renda dele.

Por isso **o descarte vem antes**. E o descarte é seguro porque foi medido: em **7 das 8**
escrituras com procurador ele aparece **ao lado** de quem representa, e a parte de verdade
entra. Na oitava não há vendedor nenhum na lista — e ali a escritura para, que é
exatamente o que ela deve fazer.

### A mesma armadilha do outro lado

`HERDEIRO(A) CEDENTE` é quem **cede**. Se `HERDEIRO` estivesse na lista de quem adquire,
essa linha bateria nas duas e a ordem das regras decidiria — dando uma resposta com cara
de certa. A palavra sozinha não diz o lado; `CEDENTE`, que está ali do lado, diz.

Daí a regra: **bater nos dois lados não é empate a desempatar por ordem — é uma
qualificação que estas listas não sabem ler**, e vira dúvida.

### Quatro palavras ficaram de fora de propósito

**`PROPRIETÁRIO` — e esta eu tinha errado.** Escrevi a régua com ela entre quem aliena, e
um ato do acervo desmente:

```
ato 222  ['Proprietário(a)', 'Vendedor(a)', 'Comprador(a)', 'Compradora', 'TESTEMUNHA']
```

**Se o proprietário fosse o vendedor, o vendedor não estaria ali.** Nos outros três atos em
que a palavra aparece não há contraparte nenhuma, e nenhum dos quatro resolve a pergunta.
Proprietário é quem consta como dono — não é, por si, quem transferiu.

`PERMUTANTE` (na permuta cada um é as duas coisas ao mesmo tempo), `HERDEIRO` (acima) e
`DECLARANTE` (nas duas linhas em que aparece o ato é dissolução de união estável, onde
quem transfere depende do que foi partilhado).

### Por que não se reaproveitou a régua que já existia

`ri_ctp._papel` responde a **mesma pergunta** para o Registro de Imóveis, e a tentação de
juntar as duas é grande — este projeto já pagou caro por vocabulário duplicado que
divergiu.

Aqui não se junta, e o motivo é medido: **`ri_partes.papel` é vocabulário controlado** —
`proprietario` em **3.894 das 3.992** linhas, `adquirente` em 1, vazio em 96 —, e ali
`proprietario` quer dizer «dono de registro», ao lado da coluna `proprietario_ativo`. Na
qualificação das notas a mesma palavra é campo livre, escrito por quem lavrou.

**A mesma palavra nos dois lugares não quer dizer a mesma coisa.** Juntar as duas funções
faria os 3.894 donos de registro do RI virarem alienantes de uma hora para outra, sem
ninguém pedir. As duas ficam separadas de propósito, com o aviso escrito nos dois arquivos
e um teste que fica vermelho se alguém as unificar sem tratar isso.

### Quem não se classifica vira dúvida, e dúvida para a declaração

O caminho fácil seria mandar só quem se reconheceu e deixar o resto de fora — e a Receita
**aceitaria**, porque o arquivo estaria bem formado. **Declaração aceita sem quem alienou
é pior que declaração recusada: a recusada volta.** É a mesma frase que já estava escrita
dentro de `notas_doi.declarar`, sobre o documento da parte.

### O que a régua diz sobre o acervo

Passada nas 37 escrituras que têm partes: **16 resolvem os dois lados, 21 param e
perguntam.** E elas param com razão — o acervo realmente só tem um lado na maioria:

```
ato 219  ['VENDEDORA', 'VENDEDORA']
ato 220  ['VENDEDORA', 'VENDEDORA', 'VENDEDORA']
ato 227  ['PROPRIETÁRIO(A)', ×3, 'PROCURADOR DO PROPRIETÁRIO']
ato 247  ['OUTORGADO']
```

> **Eram 17 e 20 antes de eu corrigir o `PROPRIETÁRIO`, e o número está aqui medido de
> novo.** A escritura 222 tem os dois lados escritos (`Vendedor(a)` e dois compradores) e
> mesmo assim passou a parar, porque o `Proprietário(a)` que está no meio virou dúvida.
> **Essa é a conta certa**: ou aquela pessoa transferiu parte do imóvel e tem de constar,
> ou não transferiu e não tem — e quem sabe é quem lavrou, não esta régua.

Nenhuma delas está marcada `com_imovel`, e por isso nenhuma entra hoje. Elas só apareceriam
se alguém as marcasse — e aí a tela diz o que falta, em vez de declarar meia transação.

---

## As duas metades que o oficial pediu

**A primeira — o campo na ficha.** Painel *O imóvel — para a DOI* na ficha da escritura,
com a operação e o tipo de imóvel **escolhidos de lista**, nunca digitados: código de
operação digitado à mão é o que a Receita recusa sem dizer qual linha, e a multa é da
serventia. Há também a marca **«este ato não tem imóvel»** — procuração, ata e declaração
não transmitem nada, e sem essa marca elas ficariam cobrando para sempre. Lista que nunca
diminui ninguém olha.

**A segunda — a conferência antes de gerar.** A tela da DOI já tinha a conta no alto
(quantas prontas, quantas paradas, e a tabela do que falta agrupada do mais comum ao menos),
no lugar certo: **antes do botão de gerar**, como a conferência do IBGE. O que faltava era
as escrituras chegarem nela.

> **E elas não chegavam por uma palavra.** Eu havia escrito a chave `texto` nos problemas
> das escrituras; `resumo_impedimentos` lê `motivo`. Elas apareceriam na lista de baixo e
> **sumiriam da conta de cima** — e a conta de cima é a que se lê antes de mandar o
> arquivo. Pior: a tela inteira estouraria ao montar o resumo.

---

## Dois defeitos que a afinidade do SQLite escondeu

`doi_transacao` e `doi_tipo_imovel` são colunas **INTEGER**. A tela grava o texto `"11"`, o
SQLite converte na entrada, calado, e a leitura devolve o número `11`.

1. **`.strip()` num número estoura a tela inteira** — a conferência morria antes de
   mostrar o que falta.
2. **`TIPO_OPERACAO` é tabela de texto.** `TIPO_OPERACAO.get(11)` não acha nada, e a
   coluna «Operação» mostrava `11` na cara de quem confere, em vez de «Compra e venda».

A conversão acontece na **entrada** e só aparece na **leitura** — é por isso que os dois
defeitos estavam a duas telas de distância da linha que os causou.

---

## O que ficou registrado em teste

`tests/test_doi_da_serventia.py`, 19 testes. Os que guardam as decisões:

- o procurador do vendedor **não** é o vendedor (as seis grafias do acervo)
- o herdeiro que cede está do lado de quem cede
- o que não se reconhece vira dúvida **e não some**
- o acento e a caixa não mudam o lado (`Vendedor(a)`, `VENDEDORA`, `DONATÁRIO(A)`)
- o proprietário **não** diz o lado, e o procurador dele continua fora
- as duas réguas de papel ficam separadas
- a escritura só com vendedoras para e diz por quê
- a dúvida diz **o nome e a qualificação** — senão a conferência vira abrir as escrituras
  uma a uma
- a conferência conta as escrituras paradas **antes** do bloco de ações
- o resumo não estoura com escritura parada
- as tabelas da Receita **não** estão duplicadas dentro do módulo de notas

---

## O que falta

**A participação de cada parte.** `conferir_participacoes` exige que a soma fique entre
99% e 100% — é validação da própria Receita —, e `nt_ato_partes` não tem coluna de
percentual. Enquanto não tiver, a declaração da escritura vai sem ela. Não inventei
divisão igual entre os alienantes: dois vendedores podem ser meeiros ou não, e o percentual
errado é declaração aceita com o número trocado.

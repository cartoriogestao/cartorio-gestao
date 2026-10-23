# Roteiro da 3.6.47 — seis relatos seus, respondidos

*30/08/2026*

---

## Primeiro: **um arquivo só, e ele é o único que você precisa aplicar**

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.47.cgu` |
| onde | `C:\Users\<usuario>\Downloads\CartorioGestao\` |
| tamanho | 2.423.724 bytes |
| SHA-256 | ver `CartorioGestao_3.6.47.cgu.sha256`, ao lado do pacote |
| arquivos dentro | 479 (nenhum do runtime) |

> **Por que o SHA-256 nao esta escrito aqui.** Este roteiro viaja **dentro** do
> pacote, e nenhum documento pode conter o hash do arquivo que o contem — ao
> gravar o numero, o arquivo muda e o numero deixa de valer. Ele fica no
> `.sha256` ao lado, que e gerado depois, e na mensagem que acompanhou a
> entrega. **Carimbo que mente e pior que carimbo nenhum**, e por isso a linha
> diz onde conferir em vez de trazer um numero que estaria errado.

Ele traz tudo o que a 3.6.46 trazia, e mais seis relatos respondidos. Se você
ainda não aplicou a 3.6.46, **aplique só esta**: o pacote é completo, não
incremental.

**O banco migra sozinho ao subir.** As tabelas novas desta leva são
`rascunhos_de_tela` (do #36) e as quatro colunas de nota de desenvolvimento em
`aj_problemas` (do #35). Nenhuma coluna é removida, nenhum dado antigo é tocado.

---

## O que mudou

### #29 — o painel mostrava o que a casa *anota*, e não o que ela *faz*

> «no painel, deveriam aparecer apenas expedientes pendentes — o painel deve
> focar nos atos em andamento e tarefas pendentes, tudo em ordem de relevância»

**Metade já estava feita, e dizer o contrário seria consertar o que não está
quebrado.** O painel já filtrava (só tarefas abertas, só expedientes não
arquivados) e já ordenava por prioridade e por prazo. Medi antes de mexer.

**A metade que faltava era «atos».** Tarefa e expediente são o que a casa anota;
a escritura em lavratura, a prenotação sem ato, o usucapião e a habilitação são o
que a casa faz — e nenhum aparecia na primeira tela. Agora há a seção **Atos em
andamento**, acima das tarefas, medida na hora das nove tabelas onde os atos já
moram (12 ms na produção), com os parados em primeiro lugar.

**E levá-lo para lá desenterrou 21.342 pendências que não existem.**

| | |
|---|---|
| atendimentos «em aberto» que a conta trazia | **21.348** |
| deles, do E-Ofício | **21.342** |
| da casa, de verdade | **6** |

São protocolos `PAGO` e `A_PAGAR` — situações que não encerram nada, porque o
botão de encerrar só nasceu em 28/08. O painel abriria dizendo **vinte e um mil
pendências**, e lista que o balcão não tem como zerar é lista que ninguém abre
duas vezes.

> **E o comentário que estava naquela linha media a coisa errada.** Ele dizia «os
> 640 abertos são todos do E-Ofício», e 640 é o número da situação `ABERTO`; a
> condição da fonte apanhava também os 16.755 pagos. **Medir o número vizinho e
> escrevê-lo como se fosse o do caso é pior que não medir.**

**`PAGO` não virou situação terminal**: pago não é entregue, e dizer que é faria
sumir da lista o serviço que o cliente pagou e ainda não recebeu.

---

### #31 — o padrão de importação, e as duas metades dele

> «criar manual e padrão de importação de acervo antigo e preenchimento de atos
> novos, possivelmente por json ou XML»

**A casa já tinha três importadores** — e nenhum é um padrão: os nomes dos campos
são os do E-Ofício (`strNomeConjuge1`), cada um tem o seu conjunto de arquivos, e
**dois dos três não têm tela**. Eles ficam, porque leem a exportação que existe.

**Primeira metade — importar acervo de outro sistema.** JSON, um arquivo só, com
os campos com os nomes das colunas desta casa (que já são português). Tela em
*Livros e acervo → Importar de outro sistema*, com **dois botões**: conferir (não
grava nada) e importar. Aqui não há como desfazer, porque o que entra vira acervo
do livro.

**Segunda metade — preencher o formulário do ato novo**, na opção que você
escolheu. O mesmo arquivo, jogando os dados na tela de lavrar em vez de gravar
direto. **São dois caminhos, e a diferença não é de conveniência:**

| | *Importar* | *Preencher o formulário* |
|---|---|---|
| o que entra | **acervo** — como veio | um **ato novo** |
| o número | o que ele já tinha | o próximo da serventia |
| folha, selo, custas | nada disso acontece | toma folha, sela e cobra |
| quantos por vez | quantos o arquivo trouxer | **um** |

**O manual baixa das cinco telas de importação**, e o arquivo baixado vem **mais
completo que o documento do sistema**: leva junto a lista de campos de cada
espécie e um exemplo pronto, montados do banco no momento do download — porque
quem o recebe está fora da serventia e não tem a tela onde essa lista mora.

**E isso consertou um defeito que já estava lá**: a tela de abrir matrícula não
tinha um único campo que voltasse preenchido — se a lavratura falhasse por
qualquer motivo, você perdia tudo o que tinha digitado, inclusive a descrição do
perímetro e o teor de abertura.

---

### #33 — pesquisar os selos emitidos

> «preciso que seja possível pesquisar os selos emitidos por data,
> especialidade, usuário»

Tela nova, com três coisas medidas nos **26.134 selos** da produção:

1. **A data de filtro é a de obtenção**, e não a de geração — esta falta em 522
   e vem em texto brasileiro, que ordena errado (`01/12` viria antes de `02/01`).
2. **«Especialidade» tem dois níveis, e os dois interessam.** A atribuição é
   grossa (NOTAS são 21.133 dos 26.134); o **tipo do ato** é fino e responde de
   verdade — 16.358 reconhecimentos de firma, 3.653 autenticações.
3. **A busca por usuário é por pedaço e sem maiúsculas.** O acervo gravou
   `ESCREVENTE` e o sistema novo grava o nome completo: procurar «beatriz» acha
   **8.956** selos, entre `ESCREVENTE` e `ESCREVENTE.C`. Busca exata acharia uma e
   calaria a outra.

**A lista tem limite e o total não.** São 26 mil selos: a lista sai cortada, e o
total, ao lado, conta todos — para que o limite não faça ninguém concluir que há
menos do que há. E há **quantos cada um selou**, por usuário, por tipo, por
atribuição, por mês e por dia: «controlar os selos» não se responde com uma lista
de 26 mil linhas.

**Esta tela só lê.** Emitir, cancelar ou corrigir selo tem consequência no razão
da serventia, e isso se faz no ato.

---

### #36 — salvar o preenchimento e continuar depois

> «em todos os atos do cartório, durante o preenchimento, é preciso ter um campo
> para salvar o progresso e continuar depois»

*Rascunhos*, no menu. **Rascunho não é ato**: não tomou número, não reservou folha
e não entrou em corrente nenhuma — pode ser abandonado sem ficar nada devendo.

**Senha, PIN e o código de segurança do formulário nunca são guardados.** O
código, se fosse, voltaria inválido e faria o próprio formulário recusar o
rascunho, sem que ninguém entendesse por quê.

**Rascunho parado há mais de 30 dias aparece marcado, e o sistema não o apaga
sozinho** — seria jogar fora trabalho de alguém sem avisar. Mas vale limpar:
rascunho tem dado de cliente dentro.

---

### #35 — o campo de retorno do desenvolvimento

> «criar um campo para completar com notas do desenvolvimento sobre a eventual
> solução ou pendência de solução de cada problema»

Cada problema ganhou nota de desenvolvimento, com cinco estados (atendido, em
andamento, depende do oficial, depende de terceiro, não será feito).

**Atendido sem prova é recusado** — «resolvido» sem dizer onde conferir é a
mesma promessa que o carimbo de versão fazia quando mentia.

**E nenhum estado fecha o problema.** Quem fecha é você, na tela: eu digo o que
fiz, você decide se resolveu.

Como não posso escrever no banco do servidor, há **importação por documento de
texto** — você sobe o arquivo e as notas entram todas.

---

### #34 — encerrar a sessão por inatividade

> «colocar o encerrar por inatividade para períodos superiores a 12h»

Feito, e configurável.

---

## O que precisa da sua decisão

1. **Suba o `NOTAS_DESENVOLVIMENTO_30-08-2026.txt`** (atualizado com esta leva)
   pela tela de importação de notas — são as notas de cumprimento dos problemas.
2. **`unit_name` em Configurações** ainda diz «Serventia Extrajudicial», e o
   papel diz outra coisa. É um clique seu.
3. **Retificação dos 23 assentos com filiação trocada** e da matrícula nº 19.132,
   com dígito verificador errado — vieram assim do E-Ofício, e retificar é ato do
   delegatário.
4. **Termo de Adesão da Receita Federal**, sem o qual o módulo de CPF não passa
   do que já faz.
5. **Sessão de 60 para 720 minutos**, se for o que você quer com o #34.

---

## Os passos

1. Feche o sistema no servidor
2. Rode `ATUALIZAR_SISTEMA.cmd`
3. Suba o sistema — **o banco migra sozinho**
4. Confira pela tabela abaixo

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| rodapé de qualquer tela | **3.6.47** |
| **Painel geral** | a seção **Atos em andamento**, e o atendimento do balcão com **6** — não com 21 mil |
| Administrativo → **Selos emitidos** | a tela existe, e o total bate em **26.134** sem filtro |
| Livros e acervo → **Importar de outro sistema** | a tela existe, com o botão de baixar o manual |
| Registro de Imóveis → **Abrir matrícula** | digite algo, force um erro: o que você digitou **volta preenchido** |
| Ajuda → **Problemas** | cada problema tem o campo de nota de desenvolvimento |

> **Se o painel mostrar vinte e um mil atendimentos em aberto, a atualização não
> subiu.** É o número mais fácil de conferir desta leva.

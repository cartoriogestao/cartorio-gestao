# Roteiro — aplicar a 3.6.1

> **SUPERADO EM 25/08/2026 — use `ROTEIRO_3.6.2.md`.**
>
> A 3.6.1 foi empacotada no fim da tarde de 25/08 e **não chegou a ser
> aplicada**. Logo depois, a mesma revisão ato por ato deu telas ao núcleo —
> abrir e encerrar livro, inutilizar folha e o encerramento diário —, e isso
> virou a 3.6.2.
>
> Este arquivo fica como registro do que a 3.6.1 trazia.

**Esta versão substitui a 3.6.0**, que foi empacotada mais cedo em 25/08/2026 e
não chegou a ser aplicada. Se você ainda tem o arquivo `CartorioGestao_3.6.0.cgu`
na pasta, **use este e não aquele**: a 3.6.0 traz o acervo do Protesto sem os
devedores, não sabe abrir registro novo pela tela e não tem a tela de numeração
que o passo 5 exige. `ROTEIRO_3.6.0.md` fica como registro do que ela trazia.

Seis passos, na ordem. **A ordem importa**: o passo 4 põe o contador do núcleo à
frente do acervo, e lavrar ato antes dele faz o primeiro ato nascer com o número
1 sobre um acervo que já chegou a 2.156.

Tempo estimado: vinte minutos, mais o que você levar decidindo os dois números
do passo 5.

---

## Passo 0 — O backup

O último foi rodado em **25/08/2026, 12:07**:

```
backup_completo_20260825_120734.zip
1.038 MB · 17.608 digitalizações · aberto e conferido depois de gravado
```

Espelhado no Proton Drive, na pasta do Provimento CN-CNJ 213/2026.

> Se você aplicar a atualização noutro dia, **rode o backup de novo** antes:
> `FERRAMENTAS\BACKUP_AGORA.cmd`. Não precisa de Administrador e não para o
> servidor.

## Passo 1 — Aplicar a versão 3.6.1

**Menu → Administrativo → Atualizações.** Só ADMIN.

1. Arquivo: `CartorioGestao_3.6.1.cgu`, na pasta `CartorioGestao`
2. **SHA-256** (cole exatamente):

   ```
   12d3f4f0e687bdde44fa6d5b477551a64e87ba7563eca75a5f92f83ee23b6fbd
   ```

3. Confirmar. O sistema fica fora do ar por alguns instantes.

Ele confere a assinatura de cada arquivo, tira um backup de pré-atualização,
aplica, sobe e testa. **Se a versão nova não responder em 45 segundos, ele
restaura a anterior sem você fazer nada.**

Confirme no fim: **Configurações** deve mostrar **3.6.1**.

## Passo 2 — Conferir que o banco migrou

O banco de produção está em um esquema anterior ao núcleo: tem 67 tabelas e
nenhuma das atribuições novas. A atualização cria **24 tabelas** na primeira
abertura.

Ensaiado sobre cópia do banco de produção em 25/08 (`ENSAIO_25_08_2026.md`):
0,1 s, **nenhuma tabela removida, nenhuma contagem antiga alterada**,
`integrity_check` ok.

Para conferir, abra qualquer tela do menu **Demais atribuições**: se ela
carregar, as tabelas estão lá.

## Passo 3 — Cadastrar a função de quem atende, se ainda não fez

Menu **Usuários**, coluna **Função**. É o que sai impresso embaixo da assinatura
nos documentos. Sem preencher, o sistema imprime "Escrevente".

## Passo 4 — Trazer o acervo das atribuições novas

**Demais atribuições → Trazer das atribuições.** Só ADMIN.

Deixe as quatro marcadas e confirme. Pode rodar quantas vezes precisar: o que já
entrou não entra de novo.

Medido sobre cópia da produção — é o que você deve ver:

| Carga | lidos | entram | rejeitados | avisados |
|---|---|---|---|---|
| Protesto | 1.370 | **1.366** | 4 | 7 |
| RCPN | 244 | **244** | 0 | 0 |
| RCPJ + RTD | 72 | **72** | 0 | 0 |
| Livro 3 | 14 | **14** | 0 | 1 |

**Leia o quadro que aparece depois.** Ele traz:

- os **4 rejeitados** do Protesto: linhas do acervo sem número, sem espécie e
  sem valor — não há o que aproveitar nelas;
- os **7 avisados**: títulos sem número no acervo que **entraram marcados**,
  porque o protesto aconteceu (têm espécie, valor e situação). Protesto que
  existiu e não aparece faz a certidão dizer que a pessoa está limpa quando não
  está;
- o **1 avisado** do Livro 3: o registro 1551 tem o livro gravado como `-` na
  origem, e entrou como Livro 3 com a anomalia anotada;
- **o que a rodada contou** — novo nesta versão:

  | Contagem | Quantos |
  |---|---|
  | devedores trazidos do acervo | **1.366** |
  | títulos sem cedente em `tbPessoa` no acervo | 458 |
  | títulos em que o acervo traz o mesmo cedente e devedor | 28 |
  | devedores sem endereço no acervo | 16 |

- e a **numeração**, que é o passo seguinte.

> **O devedor é a novidade mais importante desta versão.** Até a 3.6.0 a carga
> trazia os 1.366 títulos e **nenhum devedor** — e sem devedor a busca não acha
> ninguém por nome nem por CPF, que é justamente a pergunta do guichê. Se você
> já tinha rodado a carga antes, **rode de novo**: ela vê que os títulos já
> estão lá e traz só o que falta.

## Passo 5 — Os dois números que só você pode dizer

**Este é o passo que o ensaio de 25/08 mostrou ser indispensável — e agora ele
tem tela.** Na 3.6.0 não tinha: o roteiro pedia e não havia onde fazer.

**Demais atribuições → Numeração dos livros.** ADMIN ou gerente.

A carga semeia sozinha o contador de sete séries, do maior número que trouxe:

| Série | maior em uso | próximo |
|---|---|---|
| Apontamento do Protesto | 2.156 | **2.157** |
| Livro A — Nascimento | 19.552 | 19.553 |
| Livro B — Casamento | 1.011 | 1.012 |
| Livro C — Óbito | 1.976 | 1.977 |
| Livro E | 8.686 | 8.687 |
| RCPJ Livro A | 372 | 373 |
| RTD Livro B | 1.508 | 1.509 |

Esses números batem com o que o próprio E-Ofício declara em
`tbPropriedadeRCPN` e `tbTD_Propriedade`.

**Duas séries ficam sem contador, e não é esquecimento:**

| Série | Por que |
|---|---|
| **Registro de Protestos** | `tbAvisoProtesto` guarda o livro (4 a 9) e a folha (1 a 200) do protesto, e **nenhuma coluna com o número dele**. Não há de onde ler. |
| **Registro de Pagamentos** | o Livro 1 do acervo tem uma linha só, sem faixa de ordem aproveitável. |

Elas aparecem **em vermelho, no alto da tela de numeração**. Em cada uma,
escreva o próximo número e, ao lado, **de onde você o tirou** — "lido no Livro
9, fl. 187". Esse texto fica gravado com o seu nome e a data.

> **Antes de lavrar o primeiro protesto e o primeiro pagamento**, informe o
> próximo número de cada um. Se não informar, o primeiro nasce com o **número
> 1** — e isso é o defeito de 18/08 outra vez: número de ordem que repete o que
> a serventia já usou.
>
> O número sai do **livro físico**: o último protesto registrado no Livro 9, e o
> último pagamento do Livro 1.

O sistema **recusa** número igual ou menor que o maior já usado, e diz qual é
esse maior. Se você errou para mais, pode corrigir para menos — desde que fique
acima do que já foi lavrado.

## Passo 6 — Conferir, antes de fechar

- [ ] **Configurações** mostra **3.6.1**
- [ ] o menu **Demais atribuições** abre as quatro listas, com
      1.366 / 244 / 72 / 14
- [ ] abra a lista do **Protesto** e procure por um **nome de devedor** — antes
      desta versão isso não achava nada
- [ ] o menu do **Registro de Imóveis** tem **Usucapião extrajudicial**
- [ ] o quadro da numeração foi lido, e os dois números do passo 5 foram
      informados em **Numeração dos livros**
- [ ] abra um título de Protesto e confira que a ficha mostra os atos, a
      situação, o devedor e o que cabe lançar

---

## O que esta versão traz, além da 3.6.0

**O devedor e o cedente do Protesto.** Os 1.366 títulos do acervo entram com
quem foi protestado — nome, CPF ou CNPJ e endereço —, e a lista procura por
eles. Sem isso a certidão de protesto não teria como achar ninguém.

**Abrir registro NOVO pela tela**, nas quatro atribuições: título de protesto,
assento de nascimento/casamento/óbito, registro de RCPJ ou RTD, e registro do
Livro 3. Antes, registro novo só entrava pela carga do acervo.

**O apontamento do Protesto**, que é o primeiro ato da vida do título e não
tinha botão em lugar nenhum.

**A tela de numeração dos livros**, com os 24 livros do núcleo.

## O que a 3.6.0 já trazia, e continua

**As seis atribuições existem.** Protesto, RCPN, RCPJ, RTD e o Livro 3 do RI
ganharam domínio, carga do acervo, telas de consulta, lavratura de ato com o
lugar certo no livro certo, selo conferido e cobrança no caixa.

**O Protesto lê e escreve os quatro arquivos da CRA.** O retorno, a confirmação
e o andamento foram medidos em 572 arquivos reais; 558 deles voltam idênticos
byte a byte quando reescritos.

**Usucapião extrajudicial, como processo** — art. 216-A da LRP e arts. 747 a 761
do Código de Normas.

**A cobrança fecha no caixa.** Custas pela tabela do dia do ato, fundos
separados, sem caixa aberto não se cobra, e o recibo sai pela tela do Caixa que
já existe.

## O que NÃO entra nesta versão, e por quê

| O que falta | Por que |
|---|---|
| **Certidões** das quatro atribuições novas | é geração de documento, do tamanho do que o RI já tem |
| **Abrir e encerrar livro, inutilizar folha e encerrar o dia** pela tela | o domínio está pronto e testado; falta a tela, e o encerramento diário é coisa que a inspeção cobra |
| **SIRC, CRC, IBGE e DNV** (RCPN) | remessas externas, cada uma com o seu layout |
| Escrever o **retorno ao CRA** de verdade | o arquivo já se escreve; falta ligar ao que foi lavrado |
| A **receita de custas do RCPN** | não há: o E-Ofício mandava o `codigoAto` **vazio** nos 1.238 atos gerais do civil. Quem lavrar escolhe o item à mão até alguém medir |
| A **matrícula de 32 dígitos** do RCPN | o sistema guarda a que vier; não gera nem valida — o algoritmo oficial não foi medido |

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| A atualização diz que o SHA-256 não corresponde | Pare. O arquivo não é o que deveria ser |
| A atualização diz "ROLLBACK" | Ela voltou sozinha para a versão anterior. Nada foi perdido. Guarde `ProgramData\CartorioGestao\updates\last_result.json` e me mande |
| Uma tela de **Demais atribuições** dá erro | A migração das 24 tabelas pode não ter rodado. Me mande a tela |
| A carga diz que não achou o acervo | Ele fica em `ProgramData\CartorioGestao\acervo_eoficio.sqlite3`. Confira se está lá |
| A lista do Protesto não acha ninguém por nome | A carga não trouxe o devedor. Rode **Trazer das atribuições** de novo e leia a contagem "devedores trazidos do acervo" |
| O primeiro apontamento novo sai com número baixo | O contador não foi semeado. Rode a carga de novo e leia o quadro da numeração |

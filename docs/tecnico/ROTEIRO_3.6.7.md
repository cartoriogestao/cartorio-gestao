# Roteiro — aplicar a 3.6.7

> **SUPERADO EM 25/08/2026 — use `ROTEIRO_3.6.8.md`.**
>
> A 3.6.7 não chegou a ser aplicada. Logo depois dela veio o aviso de
> intimação, a entrega e o edital — o que fechava o dia do protesto.
>
> Este arquivo fica como registro do que a 3.6.7 trazia.

**Este é o roteiro válido.** As versões 3.6.0 a 3.6.6 foram empacotadas ao
longo de 25/08/2026 e **nenhuma delas chegou a ser aplicada** — a revisão ato
por ato continuou achando coisa a consertar depois de cada uma. Se você tiver
`CartorioGestao_3.6.0.cgu` a `_3.6.6.cgu` na pasta, **são esses que não se
usam**; pode apagá-los. Os roteiros deles ficam como registro do que cada um
trazia.

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

Espelhado na nuvem da serventia, na pasta do Provimento CN-CNJ 213/2026.

> Se você aplicar a atualização noutro dia, **rode o backup de novo** antes:
> `FERRAMENTAS\BACKUP_AGORA.cmd`. Não precisa de Administrador e não para o
> servidor.

## Passo 1 — Aplicar a versão 3.6.7

**Menu → Administrativo → Atualizações.** Só ADMIN.

1. Arquivo: `CartorioGestao_3.6.7.cgu`, na pasta `CartorioGestao`
2. **SHA-256** (cole exatamente):

   ```
   13921c82093530b1ddfc080c60478d55fda4eb91934b1275a1b03cd215939083
   ```

3. Confirmar. O sistema fica fora do ar por alguns instantes.

Ele confere a assinatura de cada arquivo, tira um backup de pré-atualização,
aplica, sobe e testa. **Se a versão nova não responder em 45 segundos, ele
restaura a anterior sem você fazer nada.**

Confirme no fim: **Configurações** deve mostrar **3.6.7**.

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
  | protestos sem livro e folha no acervo | 1 |

  E os atos que ela passou a trazer nesta versão: **1.160 protestos** (com o
  livro e a folha em que foram lavrados) e **56 cancelamentos**, todos com
  selo. É o que a certidão positiva precisa para dizer *"protestado no Livro
  X, fl. Y"*.

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

- [ ] **Configurações** mostra **3.6.7**
- [ ] o menu **Demais atribuições** abre as quatro listas, com
      1.366 / 244 / 72 / 14
- [ ] abra a lista do **Protesto** e procure por um **nome de devedor** — antes
      desta versão isso não achava nada
- [ ] o menu do **Registro de Imóveis** tem **Usucapião extrajudicial**
- [ ] o quadro da numeração foi lido, e os dois números do passo 5 foram
      informados em **Numeração dos livros**
- [ ] abra um título de Protesto e confira que a ficha mostra os atos, a
      situação, o devedor e o que cabe lançar
- [ ] abra **Demais atribuições → Livros e termos**: as 24 séries aparecem, e
      cada uma diz se tem livro aberto
- [ ] abra **Encerramento diário** e veja se há dia em atraso nos três livros
      de protocolo
- [ ] abra **Protesto — certidões**, procure por um nome que você sabe que tem
      protesto, e confira que ele aparece com o livro e a folha
- [ ] abra um registro de **RCPJ e RTD** que tenha teor e confira que a ficha
      oferece a **certidão de inteiro teor**
- [ ] abra **Protesto — retorno à CRA**: os títulos do acervo não aparecem
      (já foram devolvidos no seu tempo), e o primeiro protesto que o senhor
      lavrar aparece ali no dia seguinte

---

## O que esta versão traz, além da 3.6.6

**A REMESSA DA CRA TEM TELA** — é o passo do meio-dia do seu roteiro, e era o
maior buraco que restava no Protesto. Em **Demais atribuições → Protesto —
remessa da CRA**:

1. você escolhe o arquivo que baixou da Central;
2. o sistema **confere e mostra tudo, sem gravar nada** — quem vem, quanto,
   quem é devedor, o que o contrato recusa e o que merece um olhar;
3. você manda receber, e aí cada título é **cadastrado e apontado**, com
   protocolo e lugar no Livro de Apontamento;
4. sai a **confirmação**, para o senhor baixar e subir na CRA.

Por aqui entram **93% dos títulos desta casa**. Até agora o sistema sabia ler o
arquivo, mas não havia por onde recebê-lo.

> **O mesmo arquivo não entra duas vezes.** Se o senhor mandar de novo a
> remessa que já entrou, o sistema recusa e diz quando ela entrou — receber
> outra vez apontaria todos os títulos de novo, e apontamento não se desfaz.

**Construir essa tela achou três defeitos que já estavam no sistema**, e os três
foram consertados:

- **Arquivo com mais de um lote.** Seis dos 197 arquivos reais trazem mais de um
  lote, e **três deles são de apresentantes diferentes**. O sistema teria posto
  os títulos de um apresentante na conta de outro — e isso não apareceria na
  entrada: só quando o retorno voltasse para quem não apresentou, meses depois.
- **Eu recusava um título em cada nove.** Trinta e sete dos 343 títulos chegam
  sem data de vencimento — todos CDA, certidão de dívida ativa, que não tem
  vencimento. A própria CRA tem código para isso (irregularidade 33). O senhor
  teria de digitar à mão o que vem pronto.
- **Remessa de apresentante novo não podia ser recebida**, porque o sistema
  pedia uma letra que só se aprende num retorno anterior — e apresentante novo
  não tem retorno anterior.

**E o aviso de intimação ficou medido, para a próxima passada.** Está em
`AVISO_DE_INTIMACAO_MEDIDO.md`: nesta casa o aviso é o boleto, **sem banco
nenhum** — a serventia é a cedente —, quem entrega é o próprio cartório (os
Correios estão cadastrados e desligados), e o caminho comum é a tentativa que
não acha ninguém em casa seguida de edital: **1.068 dos 1.139 controles dizem
«Ausente»**. Duas coisas do código de barras ainda não se explicam, e por isso
o boleto não foi construído — está tudo escrito lá, com o que já se sabe.

## O que a 3.6.6 trouxe, e continua

**O sistema passou a avisar quando o banco trava.** O senhor perguntou se
valia migrar para PostgreSQL ou SQL Server; a resposta, medida, foi **não —
por enquanto**, e está inteira em `MIGRAR_DE_BANCO.md`: 111 MB, seis usuários
e **nenhuma trava em um ano de uso**.

Para que essa decisão não dependa de impressão daqui em diante, o sistema agora
**mede o próprio gatilho**:

- toda vez que uma gravação morre porque o banco estava ocupado, uma linha é
  anotada em `ProgramData\CartorioGestao\disputas_de_escrita.log`;
- o número aparece **em qualquer tela**, para o senhor e para o gerente;
- a partir de **cinco em trinta dias** o aviso muda de "uma vez ou outra é
  normal" para "já é rotina, vale conversar sobre trocar de banco".

> **Nada se perde quando isso acontece**: o ato volta atrás inteiro, e quem
> estava atendendo lança de novo. O aviso não muda o que acontece — ele só
> deixa o rastro, para a decisão vir de contagem e não de lembrança.

**E o sistema passou a se preparar para essa mudança, se um dia ela vier.** Sem
gastar nada agora: um teste passou a impedir que o código fique **mais** preso
ao banco atual do que já está. É a diferença entre uma dívida que cresce e uma
que fica parada.

## O que a 3.6.5 trouxe, e continua

**O RETORNO À CRA, e o ANDAMENTO junto com ele** — em *Demais atribuições →
Protesto — retorno à CRA*.

93% dos títulos desta casa entram pela CRA. O sistema já lia e escrevia o
arquivo de 600 posições; o que faltava era montá-lo **do que foi lavrado
aqui**. Agora a tela mostra, por apresentante, tudo o que a Central ainda não
sabe, e gera os arquivos.

> **Os dois saem juntos, e isso foi o senhor que ensinou.** O roteiro do
> protesto que o senhor pôs na pasta diz, em maiúscula: *"SEMPRE QUE GERAR
> RETORNO (FINAL), GERAR ANDAMENTO"*. Isso não está no acervo — ele guarda o
> que foi lavrado, não a ordem em que se lavra. O roteiro inteiro está
> transcrito em `ROTEIRO_DIARIO_DO_PROTESTO.md`, com o que já existe e o que
> ainda falta de cada passo do dia.

**O que vai no arquivo saiu de medição**, e não de dedução: a ocorrência do
protesto é `C` — que é o que esta casa mandou 287 vezes em 383 e a Central
aceitou, embora `C` nem esteja no contrato oficial. Pagamento vai como `1`,
desistência como `3`, cancelamento como `A`.

**Nada sai duas vezes.** Ato informado some da lista; mandar o mesmo protesto
de novo faria a Central registrar dois, e desfazer isso é trabalho de carta.

**O arquivo fica gravado inteiro**, e não só o nome: quando a Central reclamar
de um título, é esse teor que se lê.

**Cada título ganhou número de protocolo**, que é o que volta para a CRA. Ele
nasce com o apontamento, na forma que esta casa usa desde 2024 — a data em
`AAMMDD` mais o sequencial do dia. Título vindo do acervo fica com o protocolo
que já tinha.

## O que a 3.6.4 trouxe, e continua

**A CERTIDÃO DE INTEIRO TEOR do RCPJ, do RTD e do Livro 3.** Ela sai da
**ficha do registro** — é ali que o senhor está quando o cliente pede — e o
teor é o que está no livro: a certidão reproduz, não redige.

- Os textos são os desta casa: lidos nas 38 certidões de RTD/RCPJ e nas 6 do
  Livro 3 que o E-Ofício guardou.
- Sai numerada por exercício e por atribuição, com selo, cobrança, o teor
  congelado, o sha256 e o `.odt` para imprimir e assinar.
- A certidão guarda **quantos atos o registro tinha** quando saiu: quem
  conferir depois sabe se ele andou.

> **Registro sem teor não gera certidão de inteiro teor.** 24 dos 72 registros
> de RCPJ/RTD e 2 dos 14 do Livro 3 vieram do acervo **sem o texto**. Eles
> constam do livro, e o sistema diz isso: a cópia se tira do **livro físico**.
> Certidão de inteiro teor sem o teor seria papel que promete o que não
> entrega.
>
> **Registro cancelado também se certifica**, e a certidão diz que ele está
> cancelado. Esconder seria pior.

**A carga do RCPJ/RTD passou a lavrar o ato de registro**, com a folha e a
data — sem eles a certidão não tem como dizer em que folha o registro está.

> **A certidão do RCPN fica para depois**, como o senhor decidiu. Os 244
> assentos do acervo não têm teor nenhum: o E-Ofício montava a certidão dos
> campos, no modelo nacional. É o documento mais consequente do cartório, e
> merece uma passada própria.

## O que a 3.6.3 trouxe, e continua

**A CERTIDÃO DE PROTESTO** — em *Demais atribuições → Protesto — certidões*.
É o papel que este balcão mais entrega, e até agora não havia como emitir.

- Procura por **nome ou por CPF/CNPJ**, no período que você escolher (vem em
  5 anos, que é o que as 44 negativas do acervo dizem). Acha **sem acento e
  sem caixa**: digitar *josé* acha *JOSÉ*.
- Mostra o que achou — título, valor, data, **livro e folha do protesto** — e
  diz qual certidão cabe: **negativa**, **positiva** ou **de cancelamento**.
- Os textos são **os desta casa**: foram lidos nas 65 certidões que o E-Ofício
  guardou, e as colunas de cada protesto listado vieram das 19 certidões
  detalhadas do acervo.
- Sai numerada por exercício, com selo e cobrança, e **em `.odt`** para
  imprimir e assinar — como o recibo do caixa e os termos dos livros.

> **Não se emite negativa sobre quem tem protesto.** O sistema recusa, e diz
> quantos achou. Negativa errada é a certidão que faz o banco emprestar para
> quem não devia, e ela não se desfaz depois.
>
> **Apontamento não é protesto.** Só entra na certidão o título que chegou a
> ser protestado. Título apontado e pago no tríduo nunca foi protestado, e
> mostrá-lo seria certidão mentindo contra a pessoa.
>
> **O teor congela.** Protesto lavrado amanhã não muda a certidão de hoje. Se
> a certidão saiu errada, ela se **cancela** com motivo escrito — e o teor
> fica gravado como saiu, porque é a via que o cliente levou que alguém vai
> conferir.

**A carga traz o protesto e o cancelamento**, e não só o apontamento — foi a
certidão que cobrou.

## O que a 3.6.2 trouxe, e continua

**As telas dos livros.** Até agora o núcleo — a parte que cuida de livro, folha
e número de ordem — não tinha nenhuma tela: abrir livro, encerrar livro,
inutilizar folha e encerrar o dia existiam por dentro e não tinham botão. Em
*Demais atribuições*:

- **Livros e termos** — as 24 séries das seis atribuições numa tela só: qual
  tem livro aberto, em que folha está, qual o próximo número. Abre livro novo
  onde não há, e lista os encerrados.
- **A ficha de cada livro** — o termo de abertura por extenso, a
  **conferência** (o que a inspeção acharia: folha em branco no meio sem termo,
  verso pulado, número repetido), o que está escriturado, as faces
  inutilizadas, e os botões de inutilizar folha e encerrar o livro.
- **Encerramento diário** — os três livros de protocolo, com os dias que ainda
  não têm termo. Dia sem movimento também se encerra, e o termo diz isso.

**Os termos saem em `.odt`, para colar no livro de papel** — abertura e
encerramento, no mesmo formato dos termos das Notas, que você já usa.

> **O número do livro não se digita.** É o maior já usado na série mais um.
> Digitar abriria a porta para dois Livros 3 na mesma série.

### E, da 3.6.1



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
| A **certidão do RCPN** | os 244 assentos do acervo não têm teor: ela se monta dos campos, no modelo nacional do CNJ, e o senhor decidiu deixá-la para uma passada própria |
| **SIRC, CRC, IBGE e DNV** (RCPN) | remessas externas, cada uma com o seu layout |
| A **tela da remessa da CRA**, com a confirmação | é o passo do meio-dia do seu roteiro: receber o lote, apontar e confirmar |
| O **aviso de intimação, o boleto e o edital** | o seu roteiro os pede, e o sistema ainda não os tem |
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

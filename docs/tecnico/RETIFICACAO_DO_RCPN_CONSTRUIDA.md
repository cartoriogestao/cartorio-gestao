# Retificação, restauração e suprimento do RCPN — construído em 30/08/2026

Arts. 348 a 355 do Código de Normas do TJMA, **lidos no PDF que está na casa** —
e não de memória, nem do documento antigo. A leitura acertou três coisas que a
anotação anterior não tinha.

## Os três não são a mesma coisa, e o balcão os confunde

| | o quê | artigo |
|---|---|---|
| **retificação** | corrigir o que está errado no assento, na averbação ou na anotação | art. 352 |
| **restauração** | reconstituir o que foi danificado ou extraviado | art. 348 |
| **suprimento** | lançar o que falta | art. 348 |

Juntá-los num «corrigir assento» faria o escrevente escolher o caminho errado —
e o caminho errado só aparece meses depois.

**E o suprimento não exige assento**, o que é a diferença em relação à
retificação de área do RI (onde a matrícula é NOT NULL). Ali o assento **não
existe**: é o que se supre. Exigi-lo travaria justamente o instituto para o qual
ele não existe.

## A regra que muda o desenho inteiro

> **§ 2º** — «Antes de proferir a decisão, o oficial deverá realizar **consulta
> obrigatória** à Central de Informações de Registro Civil (CRC) para verificar
> a eventual existência de **duplicidade** ou a **prévia lavratura do ato em
> outra serventia**.»

**É condição de validade da decisão**, e não zelo. Até aqui, neste projeto, a CRC
era destino de carga e de comunicação; aqui ela é o que a norma exige **antes**
de decidir. Por isso `decidir()` **recusa** sem ela — não é um aviso que se pode
ignorar, é recusa, como a do usucapião sobre análise que ninguém leu.

E ela **não é um campo de texto solto**: é uma linha com data, com o que se
procurou e com o que se achou. Um campo solto seria preenchido com «ok» — e «ok»
não responde à pergunta que a correição faz. O módulo recusa registrar consulta
sem os dois.

Achando duplicidade, o **art. 365** manda comunicar **imediatamente** ao juiz
corregedor, com bloqueio cautelar do registro mais recente — e isso aparece no
andamento, com o artigo.

**Este sistema não consulta a CRC**: ele registra o que o oficial consultou. Um
botão que dissesse «consultado» sem consultar seria pior que não ter botão — ele
responderia, e responderia errado.

## As três coisas que a leitura do PDF acertou

**1. O deferido lança-se no livro CORRENTE** (§ 4º, que a anotação antiga não
tinha):

> «Deferido o pedido, a restauração ou o suprimento, que poderá ser **parcial ou
> total**, será lançado **no livro corrente em uso na serventia**, efetuando-se
> as devidas anotações e **remissões recíprocas ao assento original**, caso
> existente.»

Lançar no livro antigo seria escrever em livro encerrado; lançar no corrente sem
a remissão deixaria dois assentos da mesma pessoa **sem um apontar para o
outro** — que é como nasce a duplicidade que o art. 365 manda bloquear. A tela
diz as duas coisas no momento de amarrar o ato.

**2. A petição pode ser assinada por procurador.** O art. 352, na redação do
Provimento nº 8/2023, diz «assinada **pelo interessado, representante legal ou
procurador**». Recusar a procuração no balcão seria negar o que a norma permite.

**3. O art. 354 existe**, e é a saída quando o MP entende que o pedido exige
maior indagação: distribuição a um dos cartórios da circunscrição, com assistência
de advogado, pelo rito sumaríssimo.

## O prazo conta do pedido INSTRUÍDO

> **§ 3º** — «no prazo de até **10 (dez) dias úteis**, contados do protocolo do
> requerimento **devidamente instruído**».

«Devidamente instruído» é a condição, e não enfeite: o relógio conta do protocolo
**completo**. Contar da chegada poria o oficial em atraso por falta de documento
que o requerente ainda não trouxe — e por isso instruir é um clique separado,
que a tela cobra e que grava a data.

**Dias úteis porque o artigo qualifica.** Onde ele não qualifica — como o art.
253, § 2º da FUNAI, que diz «imediatamente» — não se empresta a folga do dia
útil. O prazo sai de `ri_schema.soma_dias_uteis`, o contador da casa.

> E ele **recebe e devolve `date`, não texto** — conferido na assinatura, e não
> suposto: passar `"2026-08-20"` estoura com «can only concatenate str». O banco
> guarda texto, e a conversão mora num lugar só.

## O pedido pode ser VERBAL, e isso importa para o balcão

> **§ 1º, III** — «verbal, hipótese em que deverá ser **imediatamente reduzido a
> termo** pelo oficial ou preposto, colhendo-se a assinatura do declarante».

Quem chega dizendo «meu nome está errado na certidão» **está formulando um
requerimento**, e mandá-lo voltar com petição é negar o que a norma permite. O
módulo **recusa abrir processo verbal sem o termo** — sem ele o pedido não existe
no papel.

## O art. 353 tem dinheiro dentro, e uma pessoa nomeada

> «Constatado que o erro é **imputável à serventia**, a retificação será
> processada de forma **gratuita** ao usuário, **independentemente da gestão
> responsável** (…) devendo o oficial (…) encaminhar a comunicação ao **Fundo
> Especial de Registro Civil (FERC)** e ao **Fundo Especial de Modernização e
> Reaparelhamento do Judiciário (FERJ)** (…) cabendo ao FERJ (…) **cobrar os
> valores despendidos do delegatário titular da serventia à época** da prática
> do ato incorreto.»

**Por isso não é caixinha de marcar.** A marca produz gratuidade, **duas**
comunicações e uma cobrança contra **uma pessoa nomeada** — e o módulo exige
fundamento próprio, além do fundamento da decisão. Marcar **abre as duas
comunicações de uma vez**: comunicar só a um deixaria o ressarcimento pela
metade, e a norma nomeia os dois.

Registrar a comunicação **confere o `rowcount`**: «não há comunicação pendente ao
FERJ neste processo» em vez de dizer «registrado» tendo mudado zero linhas — o
defeito do recibo da DOI, que fazia o escrevente ir embora achando que a
obrigação estava cumprida.

## O mandado que não precisa de «cumpra-se»

> **Art. 351, parágrafo único** — «Se houver de ser cumprido em jurisdição
> diversa, o mandado ou ofício "de ordem" será remetido, por ofício, diretamente
> ao registrador civil para que o cumpra; **independente do "cumpra-se" do juízo
> local**.»

Isto evita uma recusa comum: o escrevente que recebe mandado de outra comarca
tende a devolvê-lo pedindo o «cumpra-se» daqui. A tela diz que não precisa.

## Um achado de tela, e o filtro que ele produziu

Os módulos de norma guardam a regra com a parte que decide marcada em `**`,
porque quem lê o **código** precisa ver o que pesa. Essas mesmas constantes vão
para a **tela** — e ali os asteriscos apareciam no meio da frase: «o livro
**corrente em uso na serventia**».

As duas saídas ruins eram tirar a marcação (perdendo o destaque para quem lê o
código) ou reescrever a frase duas vezes (e as duas divergem no primeiro
conserto — a lição da `normalizar_nome`). O filtro `|forte` é a terceira: **uma
fonte só, e o destaque chega aos dois lados**. Ele **escapa antes de marcar**,
porque um filtro que devolve HTML sem escapar é a porta que alguém usa amanhã com
texto de fora.

**E o prazo saiu de dentro do `{% if %}`.** Ele só aparecia quando havia processo
— e quem abre a tela vazia é justamente quem vai abrir o primeiro, e não sabe de
quantos dias ele é.

## O que este módulo não faz

- **Não decide se o erro é da serventia** — é juízo do oficial, com efeito sobre
  o patrimônio de terceiro. *Sexta vez que esta regra aparece neste projeto:
  usucapião, fraudes, habilitação, impedimento, inacabados, e agora.*
- **Não consulta a CRC** — registra o que o oficial consultou.
- **Não lavra o ato** — quem lavra é a tela do RCPN, que tem o livro, o selo e os
  emolumentos. E ele **confere que o ato existe** antes de amarrar: sem isso
  batia na chave estrangeira e virava HTTP 500 no fim de um processo de dias, que
  foi o defeito que o teste de tela do usucapião pegou.

## Os números

| | |
|---|---|
| `rr_tjma.py` | a norma medida — 16 artigos citados |
| `rr_schema.py` | cinco tabelas: processo, consultas à CRC, peças, andamento, comunicações do art. 353 |
| `retificacao_rcpn.py` | o rito, com as recusas |
| `tests/test_retificacao_rcpn.py` | **39** testes |
| `tests/test_retificacao_rcpn_tela.py` | **26** testes |
| telas | `/rcpn/retificacoes`, `/rcpn/retificacoes/nova`, `/rcpn/retificacoes/<id>` |

## O que fica pendente do oficial

- **o canal de comunicação ao FERC e ao FERJ** — por ofício, malote, sistema?
- **a integração com a CRC**, para a consulta obrigatória sair daqui em vez de
  ser transcrita. Hoje o sistema registra o que o oficial consultou, que é o que
  se pode fazer com verdade.

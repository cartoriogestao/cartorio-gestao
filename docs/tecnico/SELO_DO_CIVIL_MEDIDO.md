# O selo do Registro Civil, medido

Medido em **27/08/2026**, em `tbSeloIndividual` do acervo do E-Ofício — 26.130
selos, dos quais **1.413 do civil** — e contra o contrato oficial do selador
(`selador.ENDPOINTS`, 181 endpoints).

O pedido do oficial foi curto: *"faça as medições para o selo funcionar"*.

---

## A correção que a medição trouxe, antes de tudo

Estava escrito neste projeto, em `CLAUDE.md` e em `ato_selado.py`:

> *"A casa selou 1.238 atos por `/selo/civil/atos-em-geral` e mandou o
> `codigoAto` **vazio** em todos. Logo não há receita de custas medida para o
> RCPN — e isso é o fato, não uma falha de leitura."*

**As duas afirmações estão erradas.**

| | |
|---|---|
| selos com `codigoAto` preenchido | **1.228** de 1.238 |
| selos com `codigoAto` vazio | 10 |

O que aconteceu foi isto: quem mediu antes olhou a **coluna `intCodigoAto`** da
tabela — que é `NULL` em todas as linhas — e não o campo **`codigoAto` de dentro
do `memJson`**, que é onde ele está.

> É a mesma lição que o oficial ensinou em 24/08/2026, quando corrigiu a
> afirmação de que só o RTD/RCPJ selava automático: **a coluna vazia não prova
> que a coisa não acontece — prova que aquela coluna não é onde ela fica.**

E a receita do RCPN existe, medida:

| Usos | Código TJ | O que é |
|---:|---|---|
| 918 | `14.5.1` | Das certidões: com uma folha |
| 237 | `14.5.6` | Certidões de inteiro teor |
| 60 | `14.5.7` | Certidão eletrônica com buscas e folhas excedentes |
| 3 | `14.6.7` | Busca: até cinquenta anos |
| 2 | `14.6.1` | Busca: até dois anos |
| 2 | `14.3.3` | Retificação, restauração ou cancelamento de registro |
| 1 cada | `14.6.6`, `14.6.8`, `14.5.2`, `14.3.1`, `16.24.4`, `16.24.4.1` | |

---

## `atos-em-geral` era o caminho ANTIGO, e 98% dele eram certidões

| Caminho | Selos | De | Até |
|---|---:|---|---|
| `/selo/civil/atos-em-geral` | 1.238 | 03/06/2020 | **23/09/2024** |
| `/selo/civil/nascimento/segunda-via` | 122 | 19/01/2023 | 30/07/2026 |
| `/selo/civil/nascimento` | 28 | 20/01/2023 | 13/08/2026 |
| `/selo/civil/casamento/segunda-via` | 15 | 23/01/2023 | 05/05/2023 |
| `/selo/civil/obito` | 8 | 27/04/2023 | 14/08/2026 |
| `/selo/civil/obito/segunda-via` | 1 | 26/01/2023 | |
| `/selo/civil/nascimento/transcricao/segunda-via` | 1 | 18/01/2023 | |

**A casa trocou de caminho em janeiro de 2023**, usou os dois em paralelo por
quase dois anos, e desde **setembro de 2024 usa só os específicos**. Dos 1.238
que saíram pelo caminho antigo, **1.215 (98%) eram certidões** — 14.5.1, 14.5.6
e 14.5.7.

Ou seja: `atos-em-geral` não era o caminho dos atos do civil. Era o caminho por
onde a certidão saía **antes** de existirem os caminhos por espécie.

---

## O contrato tem uma FAMÍLIA de caminhos por espécie

E é aqui que a regra fecha. Para cada espécie o selador tem:

```
/selo/civil/nascimento               o registro — e a primeira certidão junto
/selo/civil/nascimento/averbacao
/selo/civil/nascimento/anotacao
/selo/civil/nascimento/retificacao
/selo/civil/nascimento/segunda-via   a certidão depois da primeira
/selo/civil/nascimento/certidao-negativa
```

As três do meio são **exatamente a divisão tripartite** que a inspeção de
12/08/2026 cobra e que `rc_assento` já modela — averbação, anotação e
retificação como atos distintos.

O mesmo desenho existe para `casamento`, `obito`, `natimorto`, e para os do
Livro E (ausência, interdição, tutela, união estável, emancipação, opção de
nacionalidade), além de `nascimento/transcricao`, `casamento/transcricao` e
`obito/transcricao`.

**Por isso o caminho do civil não é uma tabela de pares: ele se compõe** da
espécie mais o tipo do ato — e **se confere contra o contrato**. Compor sozinho
produziria `/selo/civil/proclamas/averbacao`, que não existe; o contrato
responde que não existe, e a casa não sela por caminho inventado.

Está em `ato_selado.caminho_do_civil()`, com teste.

---

## O que vai dentro do envelope, medido nos 175 selos específicos

Todos os 175 — 100% — carregam a mesma estrutura:

| Campo | Presente em | O que é |
|---|---:|---|
| `codigoTipoAtoRegistro` | 36/36 dos registros | `14.a` no nascimento, `14.c` no óbito |
| `codigoTipoAtoCertidao` | 139/139 das certidões | `14.5.1` em 109, `14.5.6` em 23, `14.5.7` em 4 |
| `dadosSelo.escrevente` | 175/175 | quem praticou |
| `dadosSelo.livro` | 175/175 | |
| `dadosSelo.folha` | 175/175 | |
| `dadosSelo.termo` | 175/175 | o número de ordem do assento |
| `dadosSelo.versaoTabelaDeCustas` | 175/175 | `0120260101` — ano da tabela |
| `nomeParte` e `parte.nome` | 175/175 | o registrado |
| `papelMoeda` | **175/175** | o papel de segurança da ARPEN |
| `dadosSelo.isentoGratuito` | 19/28 nascimento, 7/8 óbito | `ISENTO` |
| `dadosSelo.motivoIsentoGratuito` | idem | `REGISTRO DE NASCIMENTO` / `DE ÓBITO` |

**O livro, a folha e o termo o sistema já tem** — são do ato, e é por isso que o
selo tem de ser pedido *depois* de o ato ser lavrado.

**A isenção é da lei, e está no próprio código**: `14.a` é *"Registro de
nascimento, bem como pela primeira certidão respectiva. **Isento**"*, e `14.c` o
mesmo para o óbito.

---

## O que a medição não resolveu, e o oficial decidiu em 27/08/2026

> As três perguntas abaixo ficaram como estavam quando foram feitas, com a
> resposta dele em seguida. **Pergunta apagada é decisão que ninguém consegue
> reconstituir depois.**

### 1. O papel de segurança da ARPEN

Os 175 selos específicos levam `papelMoeda`:

```json
{"codigo": "7225319", "fornecedor": "ARPENBRASIL", "utilizado": false}
```

O E-Ofício controlava isso numa tabela própria — `tbPapelMoedaRCPN`, com **510
folhas numeradas**, série (`BA`, `HA`), remessa, tipo de papel (24 tipos:
*"Azul (Certidão Portável)"*, *"Rosa"*…) e a marca de usado. **O sistema novo
não tem esse controle de estoque.**

Sem o número do papel, não sei se o selador aceita o pedido. Isso muda o
tamanho do trabalho, e por isso é a primeira pergunta.

> **DECIDIDO: construir o controle.** É `papel_seguranca.py`, com tela em
> *Registro Civil → Folhas de segurança* e carga que traz as 510 folhas do
> E-Ofício — 161 usadas e 349 em branco.

### 2. Três espécies sem caminho

O sistema modela sete espécies; o contrato responde por quatro:

| Espécie do sistema | Caminho | |
|---|---|---|
| NASCIMENTO · CASAMENTO · OBITO · NATIMORTO | `/selo/civil/<espécie>` | ✅ fecha |
| **CASAMENTO_RELIGIOSO** (Livro B-Auxiliar) | ? | o contrato não tem `casamento-religioso` |
| **PROCLAMAS** (Livro D) | ? | existe `/selo/civil/casamento/habilitacao` |
| **OUTRO** (Livro E) | ? | o Livro E se parte em **seis** caminhos |

> **DECIDIDO**: o casamento religioso sela pelo caminho do casamento — o que
> muda é o livro, não o ato; proclamas sela pela habilitação; e o **Livro E se
> partiu em seis espécies** no sistema, cada uma com o seu nome na tela.
> `OUTRO` fica para o que não é nenhuma das seis, e é honesto que ele não tenha
> caminho de selo.

### 3. A primeira certidão está dentro do selo do registro

`14.a` diz *"registro de nascimento, **bem como pela primeira certidão
respectiva**"*. Então a primeira certidão de um assento lavrado aqui **já está
paga e selada** pelo selo do registro.

O sistema hoje emite certidão como ato separado, que pediria selo próprio.

> **DECIDIDO**, com as palavras dele: *"acho que o selo do primeiro registro já
> considera a certidão, mas atos como averbação e certidão, vai dois selos na
> certidão, não há problema nisso."*

---

## O que já está no código depois desta medição

- `ato_selado.caminho_do_civil(especie, tipo)` — compõe e confere contra o
  contrato;
- `caminho_do_ato(tabela, tipo, especie)` — o civil sai da tabela de pares;
- as três telas do RCPN passam a espécie do assento;
- os quatro testes que guardam isso, incluindo um que exige que o civil **não
  volte** para a tabela de pares.

### O envelope, montado em 27/08/2026

Depois que o oficial decidiu as três perguntas, o envelope ficou de pé:

```json
{
  "codigoTipoAtoRegistro": "14.a",
  "dadosSelo": {"escrevente": "…", "livro": "24", "folha": "166",
                "termo": "19552", "versaoTabelaDeCustas": "0120260101",
                "isentoGratuito": "ISENTO",
                "motivoIsentoGratuito": "REGISTRO DE NASCIMENTO"},
  "nomeParte": "…", "parte": {"nome": "…"},
  "papelMoeda": {"codigo": "7225319", "fornecedor": "ARPENBRASIL",
                 "utilizado": false}
}
```

**O nome do campo do código muda com o ato** — `codigoTipoAtoRegistro` no
registro, `codigoTipoAtoCertidao` na certidão. Mandar o nome errado é o
aparelho recusar.

**O item da tabela de custas tem duas procedências, e elas ficam marcadas.**
`MEDIDO` é o que a casa mandou de verdade (`14.a` em 18 selos, `14.c` em 8,
`14.5.1` em 109); `TABELA` é o que saiu da tabela de preços do TJMA, lida pela
descrição do próprio item — *"Assento de natimorto, bem como pela primeira
certidão respectiva. Isento"* é `14.d`, e não há como isso ser outra coisa.
Onde não há nem um nem outro, o valor é `None` e o ato sai sem selo.

**A isenção vem da lei e vai escrita.** `14.a`, `14.c` e `14.d` dizem *Isento*
na própria tabela, e o selo leva `isentoGratuito` com o motivo — como o
E-Ofício mandava.

**A versão da tabela de custas é configuração**, e não constante: é um número
que o TJMA publica com cada tabela (`01` mais a data em que ela passou a valer),
e muda quando sai tabela nova. Fica em `selo_versao_tabela_custas`, com o valor
medido de 2026 como padrão.

### A folha só se gasta se o selo sair

A próxima folha da gaveta é **reservada** antes do pedido e vai dentro do
envelope; a baixa acontece **depois** de o aparelho responder. Se ele não
responder, a folha continua em branco — porque ela continua em branco na gaveta
de verdade.

E sem folha em branco no estoque, o ato é lavrado e a tela diz que não há papel:
selar sem papel seria prometer uma certidão que não tem onde ser impressa.


---

# As outras atribuições, medidas em 27/08/2026

Depois de fechar o civil, medi os envelopes das outras famílias — para saber o
tamanho do que falta, e não para construir por semelhança.

## A versão da tabela de custas muda com a ATRIBUIÇÃO

**Isto corrigiu um defeito que eu tinha acabado de introduzir.** Eu havia posto
o valor do civil numa configuração única, como se valesse para a casa inteira.
Os selos de 2026 desmentiram na mesma tarde:

| Atribuição | Versão |
|---|---|
| civil | **01**20260101 |
| imóvel | **02**20260101 |
| protesto | **03**20260101 |
| RTD/PJ | **04**20250101 |
| notas | **05**20260101 |

Os dois primeiros algarismos são o número da **seção da atribuição** na tabela
do TJMA; o resto é a data em que a tabela passou a valer. Mandar `01` num selo
de protesto seria dizer ao aparelho que o ato foi cobrado por outra tabela.

Agora o prefixo é medido e mora no código; só a data é configuração
(`selo_tabela_custas_em`), porque muda quando o TJMA publica tabela nova.

## Cada família tem o seu envelope, e eles não se parecem

| Caminho | Selos | O que vai dentro |
|---|---:|---|
| `/selo/notas/reconhecimento-firma` | 13.776 | `escrevente`, `natureza`, `nomesReconhecido`, `ato` |
| `/selo/notas/autenticacao` | 3.664 | `escrevente`, `quantidade`, `ato` |
| `/selo/notas/cartao-assinatura` | 2.667 | `escrevente`, `partes`, `ato` |
| `/selo/imovel/prenotacao` | 829 | `dadosSelo{codigoTipoAto, naturezaTitulo, livro, partes, isento, reterIss, percentualDesconto…}`, `protocolo` |
| `/selo/imovel/certidao` | 667 | plano: `codigoTipoAto`, `escrevente`, `isento`, `partes`, `quantidade`, `reterIss` |
| `/selo/protesto/*` | 1.308 | `convenio`, `natureza`, `selo{escrevente, protocolo, valorTitulo, livro, folha}`, `ato`, `partes` |

**Nenhuma delas se monta a partir da outra.** O civil aninha em `dadosSelo`; as
notas mandam plano; o imóvel muda de forma entre `prenotacao` e `certidao`.

## O Protesto sela uma vez por ITEM DE CUSTA, e não uma vez por ato

Esta é a descoberta que impede de copiar o desenho do civil.

Na **retirada**, os itens `17.10.1`, `17.4` e `17.2` aparecem **49 vezes cada** —
sempre os três juntos, no mesmo ato. No **pagamento**, `17.2` (163), `17.4`
(143) e `17.10.1` (142). Na **baixa-cancelamento**, `17.2` (57), `17.3` (55) e
`17.5.1` (51).

> É o «um selo por etapa» que o levantamento do Protesto já tinha achado — e que
> `atribuicoes.ITENS_DE_CUSTA_POR_CAMINHO` já mede. O que muda é o desenho: **um
> ato do Protesto gera N selos**, e não um.

E há uma coisa que ainda não sei: **`natureza.tipo` varia dentro do mesmo
caminho** — no pagamento, `8` em 431 selos e `0` em 34; no título, `8` em 53 e
`0` em 17. Logo não sai do caminho: sai de alguma outra coisa, que não medi.

**Por isso não construí o envelope do Protesto.** Construir sobre uma leitura
parcial é o que este projeto já pagou caro para não fazer.

## O que isso quer dizer para o próximo passo

- **Notas** é o maior volume (20 mil selos) e o envelope mais simples — quatro
  campos. É por onde eu começaria.
- ~~**Protesto** precisa antes de duas medições~~ — **feito em 27/08/2026**, e
  as duas respostas estão abaixo.
- **Imóvel** tem duas formas diferentes na mesma atribuição, e a prenotação leva
  desconto e retenção de ISS — que é dinheiro, e merece medição própria.


---

# O selo do Protesto, fechado em 27/08/2026

## A `natureza.tipo` estava no contrato — eu é que não tinha olhado

Escrevi, algumas horas antes, que ela «sai de alguma outra coisa, que não
medi». Saía do `selador-doc`, que está na pasta do E-Ofício desde sempre:

```
0 Intimação por Carta Protocolada    6 Certidão por inteiro teor
1 Intimação por Carta Registrada     7 Protesto de título
2 Intimação por Edital               8 Pagamento de título
3 Certidão por nome                  9 Retirada de título
4 Certidão por título acrescido     10 Outro
5 Certidão por título digitado
```

Com o enum na mão, a medição encaixa inteira: pagamento **8** (431 selos),
retirada **9** (147), certidão **0** (57 de 57).

> **Antes de dizer que um campo não se explica, vale abrir a documentação que
> já está na casa.** Eu tinha lido o contrato para os endpoints e não para os
> enums.

E a intimação é a única cuja natureza depende de *como* ela aconteceu — o que o
sistema já grava (`PESSOAL` ou `EDITAL`). Pessoal é **Carta Protocolada**, e não
Registrada: quem entrega nesta casa é a própria casa, e as 1.618 entregas saíram
com taxa de AR **zero**.

## Um selo por item cobrado — decisão do oficial

> *"Um selo por item cobrado"* — 27/08/2026.

É o que o E-Ofício fazia: na retirada, `17.10.1`, `17.4` e `17.2` aparecem **49
vezes cada, sempre os três juntos**. E respeita a regra que já valia para a
cobrança: o que sai é do caso concreto, e não da média.

**Cada item leva a sua própria referência** — `pt_atos:12:17.4`. Não é detalhe:
é dela que sai o SID, e é o SID que faz o aparelho devolver o selo que já existe
em vez de vender outro. Com uma referência só para os três itens, **o aparelho
devolveria o mesmo selo três vezes**.

**Sem item marcado, não sai selo**, e a tela diz isso. É a consequência direta
da escolha, e é melhor dita que silenciosa.

**O `convenio` não vai**: ausente em 440 dos 465 selos de pagamento.

## Duas colisões de palavra, no mesmo dia

**`natureza.tipo` da certidão não é o do título.** Escrevi `3` porque no enum do
título o 3 é «Certidão por nome» — mas a certidão usa outro schema, com enum
próprio, onde por nome é `0`. Quem me pegou foi o meu próprio comentário, que
dizia «57 de 57 com tipo 0» ao lado de um código que dizia 3.

**`CANCELAMENTO` quer dizer duas coisas.** A baixa do protesto (`pt_atos`) é
natureza 9; a certidão de cancelamento (`pt_certidoes`) é certidão como as
outras, e sai por busca de nome. A tabela desempata.

> **A mesma palavra em dois lugares não quer dizer a mesma coisa** — e este
> projeto aprendeu isso duas vezes em meia hora.

---

# De onde vêm os itens — a correção de 27/08/2026

O oficial corrigiu o desenho em duas frases, e as duas mudaram coisas
diferentes:

> *"Todos os selos são automáticos, escolhendo pelo item da tabela de
> emolumentos."*
>
> *"No E-Ofício o selo é emitido com base no protocolo e caixa. Os itens que
> abriram o protocolo e caixa são os que são emitidos selos no fim."*
>
> *"O selo deve sair no ato; protocolo é apenas fonte de informações."*

## O que a medição confirmou

Cruzei 120 protocolos de 2026 com os selos que saíram deles:

| | |
|---|---|
| Protocolos com **exatamente** os selos dos itens que os abriram | **101** |
| Divergem | 16 |
| Sem itens no protocolo | 3 |

E um detalhe que eu não teria adivinhado: **a conta é por unidade, e não por
item**. O protocolo `2026.08.103` abriu **um** item `13.18` com quantidade
**10**, e saíram **10 selos** de `13.18`. Dez cópias autenticadas são dez selos.

## O desenho que ficou

| | |
|---|---|
| **Quando** | no ato, quando ele é praticado |
| **Quais itens** | os do protocolo — um selo por unidade |
| **Sem protocolo** | os itens marcados para cobrar |
| **Referência (SID)** | uma por item: `pt_atos:12:17.4` |

**O protocolo é fonte de informação, e não etapa do selo.** Não há tela de
"selar o protocolo": o selo pertence ao ato, e é lá que ele sai.

## O sistema já tinha o lugar

`cx_protocolo_atos` chegou da migração com **32.416 linhas** — praticamente as
mesmas 32.424 de `tbProtocoloGeralCustas` — e com `codigo_ato`, `quantidade` e
duas colunas `selo` e `selo_texto` já esperando. A estrutura estava pronta antes
de alguém perguntar por ela.

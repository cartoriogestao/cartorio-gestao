# A Certidão Eletrônica do ON-RCPN — o item 2 do cronograma

> «siga no desenvolvimento das integrações até terminar de todas, sem minha
> intervenção» — o oficial, 03/09/2026, depois de fazer o cadastro na
> homologação.

É a **maior entrega para o balcão** das quatro Centrais que faltavam: além de
emitir a certidão eletrônica, ela traz a **fila de pedidos de sete módulos** —
e dois deles não pedem certidão: pedem que a serventia **lavre um registro**.

---

## 1. O que passou a existir

| | |
|---|---|
| `onrcpn_certidao_api.py` | o transporte — **10 caminhos**, medidos no contrato |
| `rc_pedidos_schema.py` | `rc_pedidos` (a fila) e `rc_certidoes_eletronicas` |
| `rc_pedidos.py` | a corrente pedido → assento → certidão → cumprir |
| `rc_pedidos_web.py` | onze rotas, em **Registro Civil → O balcão → Pedidos da Central** |
| `templates/rcpn_pedidos.html` · `rcpn_pedido.html` | a fila e a ficha |

**No menu:** *Registro Civil → O balcão → **Pedidos da Central***. Fica no
balcão, e não com as comunicações: aquelas são o que a casa **deve mandar** e se
pensam por prazo; esta é trabalho que **chegou** e espera resposta.

---

## 2. Os sete módulos, e a diferença que muda o ato

Eles **não estão numa lista fechada do contrato** — o campo `modulo` é um
`string` com o exemplo `"CRC"`. Os sete estão na **prosa** da descrição de
`obter-pedidos`, e foram transcritos um a um:

| | |
|---|---|
| `CRC` | pedidos de certidão no módulo do Provimento n. 149 |
| `REG` | pedidos de certidão do site `registrocivil.org.br` |
| `JUD` | pedidos de certidão nos módulos CRC-Jud ou Serp-Jud |
| `EPR` | pedidos feitos na plataforma do e-Protocolo |
| `RSE` | pedidos de certidão pelo módulo «Registre-se» |
| **`P13`** | **solicitações de REGISTRO de nascimento** nas Unidades Interligadas |
| **`EOB`** | **solicitações de REGISTRO de óbito** pelo módulo e-Óbito |

**Os dois últimos são outro ato.** Um se emite; o outro se **lavra** — toma
número, ocupa folha, gasta selo e entra na corrente de hash. Por isso:

* **este módulo não lavra nada** (a quinta vez neste projeto, depois do
  usucapião, das fraudes, do CNIB e da CENPROT);
* a ficha do `P13`/`EOB` **avisa** e manda lavrar na tela do Registro Civil;
* `atender()` **recusa** cumprir um deles pelo caminho da certidão, com a frase
  que diz onde se faz;
* existe a situação **`REGISTRADO`**, que é o que tira da fila o que já virou
  livro — e o botão que a produz **não cria assento nenhum**, e há teste que
  conta os assentos antes e depois.

---

## 3. As armadilhas medidas do contrato

**Todas foram achadas abrindo o `certidao_swagger.json`**, e não relendo o
código. É a lição da CENPROT (seis defeitos meus só apareceram quando o teste
abriu o contrato), da ONRTDPJ, e do e-Proclamas de horas antes.

### 3.1. O contrato não declara endereço nenhum

`servers` vem **nulo**. O endereço sai da página de documentação —
`certidaoh.registrocivil.org.br` —, e ela tem o **«h» de homologação**. Há teste
que fica vermelho no dia em que declararem `servers`, porque nesse dia a BASE
passa a ter fonte melhor que uma página de documentação.

### 3.2. A mesma Central, dois formatos de CPF

| | e-Proclamas | Certidão Eletrônica |
|---|---|---|
| CPF | `00000000191` — **cru** | `000.000.001-91` — **com máscara** |
| data | `28/03/2025` | `18/07/2024` — igual |
| matrícula | 32 dígitos | 32 dígitos — igual |

Medido nos **cinco** exemplos de CPF deste contrato: todos pontuados; nenhum
exemplo daquele. As duas funções se chamam `cpf_para_a_central` em módulos
diferentes e fazem o **oposto** — e há teste que compara as duas, para um
conserto distraído não igualar duas Centrais que não são iguais.

> Isto é medido nos **exemplos**, e não numa chamada real. Se a Central recusar
> o CPF com 422, é aqui que se olha primeiro, e é uma linha.

### 3.3. Dois formatos de dinheiro dentro da mesma API

```
cota_emolumentos    "R$ 10,00"   com símbolo e VÍRGULA
valor_emolumentos   "1.00"       nu e com PONTO
deposito_previo     "43,76"      o que ela DEVOLVE, com vírgula
```

Quem subtrair o depósito do valor final sem converter lê **quarenta e três**
onde estão quarenta e três reais e setenta e seis centavos.

### 3.4. `numero_pedido` tem três nomes e dois tipos

```
obter-pedidos      devolve   pedido_certidao_id   integer
enviar-pedidos     exige     numero_pedido        STRING
rejeitar-pedidos   exige     numero_pedido        NUMBER
```

É a armadilha do `cd_pedido` da CENPROT outra vez. `TIPO_DO_NUMERO_DO_PEDIDO`
declara os dois, e há teste que lê os dois do contrato.

### 3.5. Fora de São Paulo, `quantidade_averbacao` vai NULA

Está na descrição do próprio caminho: «quando a solicitação for de **outro
estado**, envie o valor NULL». O Maranhão é outro estado — e o campo é
**obrigatório**, de modo que ele vai **presente e nulo**, e não ausente. A tela
nem mostra o campo, e diz por quê.

### 3.6. O arquivo não vem em base64

`arquivo: {type: string, data: array[integer]}` é um **`Buffer` do Node**
serializado em JSON. Quem tentar `b64decode` recebe erro; quem tentar `.encode()`
grava um PDF corrompido que só aparece ao abrir.

### 3.7. `certificate-file` é o único dos dez sem `security`

Os outros nove declaram `BearerAuth`. É **omissão do contrato**, e não caminho
aberto — mesmo cadastro, mesmo token, mesma Central. Há teste que fica vermelho
quando corrigirem, para a correção não passar despercebida: é a decisão do
`http://` no WSDL da CRA.

### 3.8. O `410` da assinatura não tem `success`

Todas as outras respostas declaram `success` (booleano). O `410 Certidão
cancelada` devolve `{data: {status}, message}` — e tratá-lo pela régua geral
daria «a Central respondeu sem dizer se deu certo» a quem precisa ler «esta
certidão está cancelada».

### 3.9. Só o `N` do `tipo_registro` do pedido está medido

Dentro do pedido, `tipo_registro` vale `"N"` — e no esquema `Certidao` o campo
de mesmo nome vale `"nascimento"`. **Duas palavras iguais, dois vocabulários.**
O `C` e o `O` são a leitura óbvia da inicial, e leitura óbvia não é medição: a
ficha mostra a letra crua e diz que só o `N` está conferido.

---

## 4. HTTP 201 não basta — e desta vez havia como saber

No e-Proclamas, horas antes, eu tratei HTTP 200 como sucesso porque tinha lido
só a `description` de cada resposta. Aqui o corpo declara **`success`**, e
`_resposta_ou_erro` **exige que ele seja verdadeiro**: código HTTP bom com
`success: false` levanta recusa, com a frase da Central junto.

E o `422` traz o `message` como **um objeto por campo**
(`{"registro.matricula": ["..."]}`), e não como frase. Ele vai **inteiro** para
a tela: resumir aqui esconderia justamente o campo que o escrevente precisa
corrigir.

---

## 5. O casamento do pedido com o assento é pela matrícula, e só por ela

O pedido traz também livro, folha e número, e seria fácil casar por eles.
**Não se casa**: os números do livro reiniciam por volume nesta casa — é a
pendência de numeração do casamento, declarada desde 29/08/2026 —, e um
casamento errado mostraria ao balcão **o registro de outra pessoa**. Ninguém
desconfia de uma ficha que abre.

Quando a matrícula casa, **o nome também se compara**, e a divergência vira
**aviso, e não recusa**: o nome muda legitimamente — o de casada muda em 17 dos
20 casamentos desta casa.

E quando não casa, **a ficha diz o que fazer**, e oferece amarrar à mão com o
motivo escrito («conferido no livro A-12, fl. 34»).

---

## 6. O que a casa manda, e o que ela recusa mandar

### 6.1. O óbito leva os três campos que o revisor cobrou

O **achado 2** do revisor registral (31/08) dizia que causa da morte,
sepultamento e testamento não tinham onde ser informados. **Conferido hoje: está
fechado** — os cinco campos estão em `CAMPOS_DO_TERMO_POR_ESPECIE["OBITO"]`, na
rota de lavrar e no formulário. E a Central pede exatamente esses nomes:

```
causa_morte                    ← rc_assentos.causa_morte
nome_medico · crm_medico       ← atestante · atestante_documento
local_sepultamento_cremacao    ← local_sepultamento
```

> **Lista de pendência que envelhece faz planejar trabalho já feito** — terceira
> vez neste projeto. Antes de refazer o achado, medi.

### 6.2. O sexo em branco **não** vira «ignorado»

Medido na produção: `rc_pessoas.sexo` tem `M` em 751, `F` em 719 e **vazio em
14**. `ignorado` é uma resposta que alguém pode ter dado; vazio é campo que
ninguém preencheu. **Campo ausente não afirma nada.**

### 6.3. O natimorto não vira «nascimento»

A Central declara **quatro** tipos, e nenhum é natimorto. Mandá-lo como
nascimento afirmaria nascimento com vida — a mesma recusa que
`rc_certidao_odt` já faz no papel.

### 6.4. O «nome que passou a utilizar» não vai, e a tela diz

A casa guarda o nome de cada cônjuge; **qual deles é o de antes e o de depois**
não está em campo nenhum. É justamente o campo pelo qual a certidão de casamento
existe — e por isso o aviso diz o que precisaria mudar na ficha do assento.

### 6.5. A existência de bens que não se entende fica em branco

A Central aceita três palavras (`sim`, `nao`, `ignorada`) e a casa guarda texto
livre. O que se reconhece traduz; o resto fica vazio **com aviso** — mandar
«nao» sobre um texto que não se entendeu afirmaria que o falecido não deixou
bens.

### 6.6. O inteiro teor sai do TERMO, e os 244 do acervo não têm

O contrato pede `texto_certidao`; o que a casa tem é o `teor` do assento. **Os
assentos vindos do E-Ofício estão todos sem ele** — para eles a cópia se tira do
livro de papel, e a conferência **impede** em vez de inventar texto.

Isto **não fecha o achado 3** do revisor (o civil não emite certidão de inteiro
teor **em papel**): fecha o caminho eletrônico, quando há teor.

### 6.7. Não se compra selo por aqui

Esta casa **nunca selou certidão eletrônica**, e escolher um caminho de selo por
semelhança seria assinar por quem selou. Se já houver selo, digita-se.

---

## 7. A assinatura acontece na Central — e isso resolve o que o A3 impede

`assinatura_digital.py` registra a medição: os dois drivers PKCS#11 desta
máquina dão **segmentation fault** ao carregar, e um Flask que os carregue leva
o balcão inteiro junto. Aqui `POST /sign-certificate-json/{id}` assina **do lado
de lá**, e o que volta é um `link_assinatura` e um `id_assinatura`.

**O que este módulo continua não afirmando é que a firma é válida** — é a mesma
regra daquele: conferir a cadeia da ICP-Brasil exige âncoras e lista de revogação
que esta casa não tem.

---

## 8. Corrigir não queima o identificador

`PUT /certificate-json/{id}` existe, e o caminho oposto é pior: cancelar e criar
de novo dá um `certidao_id` **novo** — e o pedido pode já ter recebido o antigo
como `id_verificador`, deixando quem está do outro lado com um número que não
aponta para nada. O botão «Corrigir na Central» reenvia os dados de agora e
**mantém o identificador**; o tipo de registro não vai, porque a própria
descrição do caminho diz que ele não se altera.

> **O varredor de função órfã achou este botão faltando.** Eu havia escrito
> `atualizar()` no transporte e nenhuma tela a chamava — o defeito que mais se
> repetiu neste projeto, pela enésima vez. Ele também achou
> `eletronicas_do_assento`, que virou o quadro **«já saiu certidão eletrônica
> deste mesmo registro»**: um segundo pedido do mesmo assento chega com
> frequência, e quem não vê isso **cria outra**, que custa.

---

## 9. O que não foi ligado, e por quê

**Os dois caminhos de arquivo PDF** (`POST` e `PUT /certificate-file`) estão
medidos e **declarados em `CAMINHO`** — para ninguém os reinventar achando que
sumiram —, e não estão ligados:

* o `POST` declara as três partes como `string` solto e o `PUT` as declara com
  os `$ref` dos esquemas: **o mesmo conceito, duas formas, no mesmo contrato**;
* o PDF que esta casa sabe montar é o da certidão **de papel**, do molde que o
  oficial desenhou à mão. Mandá-lo como a certidão **eletrônica** é decisão de
  quem assina, e não dedução deste módulo.

---

## 10. O que fica guardado, e o que não

**O teor congela.** O que a Central mandou fica como veio, em JSON; ela pode
mudar o dado dela amanhã, e o que a casa respondeu foi sobre aquilo. O que a
casa mandou também congela, com `sha256`.

**O PDF não mora no banco.** O arquivo é da Central e se busca nela
(`GET /get-certificate-json/{id}`, que devolve também a situação corrente).
Guardá-lo aqui poria binário num banco que **viaja no backup** — e o backup já
saiu da serventia. A rota `/pdf` o serve **em linha**, com os cabeçalhos de
segurança da casa (`nosniff` + política que proíbe script e moldura).

**O ambiente entra nas duas chaves únicas** — `(ambiente, modulo,
numero_pedido)` e `(ambiente, certidao_id)`. É a lição da CENPROT: homologação e
produção numeram no mesmo intervalo, e sem o ambiente o primeiro pedido de teste
ocuparia o lugar do primeiro de verdade, **e o de verdade não entraria, sem erro
em lugar nenhum**.

---

## 11. Rejeitar e dispensar são coisas diferentes

| | o que faz | o que exige |
|---|---|---|
| **Rejeitar** | sobe o motivo **para a Central**, e o requerente o lê | motivo escrito |
| **Dispensar** | tira da fila **daqui**; a Central continua com o pedido em aberto | motivo escrito, e a tela diz que ela continua esperando |

«Não foi possível atender» não diz o que fazer; «o registro não é desta
serventia» diz.

---

## 12. O que rodou

| | |
|---|---|
| `tests/test_onrcpn_certidao_api.py` | **48** — todos abrem o contrato e comparam |
| `tests/test_rc_pedidos.py` | **34** — o domínio, sem rede |
| `tests/test_rc_pedidos_web.py` | **34** — as telas, com o transporte de mentira |
| varredores (função órfã · CSRF · débitos do balcão · portabilidade · menu · esquemas) | verdes |
| `ruff check` nos módulos novos | limpo |

**Nenhum teste fala com a Central.**

---

## 13. O que depende do oficial

1. **O token do IdRC** — o cadastro de homologação foi feito em 03/09/2026. O
   que chega é um **par** (`clientID` + `client secret`), e não um token pronto;
   o `/api/auth` que emite o token **não fica nos endereços da API** (medido:
   404 nos dois), e vem no manual que acompanha a aprovação. **É o mesmo token
   do e-Proclamas** — um cadastro serve às duas.
2. **O endereço de produção**, que nenhum dos dois contratos publica.
3. **Um pedido real na homologação**, que é o que fecha as três coisas
   derivadas: o formato do CPF, as letras `C` e `O` do tipo de registro, e o que
   o `id_externo` significa do lado de lá.

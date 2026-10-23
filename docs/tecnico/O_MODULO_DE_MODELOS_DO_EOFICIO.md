# O módulo «Modelos» do E-Ofício — medido e copiado

> «copie o modulo de modelos do e-oficio e vamos implementar no nosso sistema»
> — o oficial, 07/09/2026.

---

## 1. O que o módulo do E-Ofício é

Uma tabela e uma tela. A tabela é **`tbModelosRCPN`**, com **13 linhas** nesta
casa; medida no `bdCartorio` do SQL Server em 07/09/2026, só leitura.

Cada linha é um **documento avulso** que o balcão escreve em volta do ato — e
**não** é o termo do livro. Os treze, com a espécie de cada um:

| # | nome | espécie |
|---|---|---|
| 1 | CERTIDÃO DE NASCIMENTO 1ª Via | nascimento |
| 2 | Certião inteiro teor *(sic)* | nascimento |
| 3 | Investigação da paternidade de filhos — Modelo Oficial Juiz | nascimento |
| 4 | Registro Tardio | nascimento |
| 7 | Termo de Alegação de Paternidade | nascimento |
| 8 | Termo de Gêmeos | nascimento |
| 9 | Comunicação de Casamento para o Registro de Nascimento | casamento |
| 10 | Certidão de Casamento | casamento |
| 11 | Termo | nascimento |
| 12 | Certidão de Obto *(sic)* | óbito |
| 13 | Casamento Religioso | casamento |
| 14 | Termo | óbito |
| 15 | CERTIDÃO DE NASCIMENTO 2° VIA | nascimento |

**As chaves 5 e 6 não existem** — foram apagadas. E **«Termo» aparece duas
vezes**, nas linhas 11 e 14, em espécies diferentes: é por isso que a chave
única desta casa é `(especie, nome)`, e não só o nome.

---

## 2. Cinco das onze colunas nunca foram usadas

| coluna | o que é | usada? |
|---|---|---|
| `strDescricao` | o nome | **sim**, nas 13 |
| `intTipoRCPN` | 1 nascimento · 2 casamento · 3 óbito | **sim**, nas 13 |
| `memTexto` | o texto, em RTF | **sim**, nas 13 |
| `bitAtivo` | se aparece na lista | **sim** — as 13 ativas |
| `memTextoPadrao` | — | **NULA nas 13** |
| `memTextoInteiroTeor` | — | **NULA nas 13** |
| `memCertidaoInteiroTeor` | — | **NULA nas 13** |
| `bitGuiaCliente` · `intGuiaCliente` | — | **False/0 nas 13** |
| `intTipo` | — | **NULA nas 13** |

**Copiar coluna vazia seria copiar a intenção de alguém, e não o módulo.** A
tela teria campo que ninguém preenche e o escrevente perguntaria para que
serve. O que o módulo **é**, medido pelo que ele guarda, são quatro coisas:
**nome, espécie, texto e se está ativo** — e é essa a tabela desta casa.

> **E `tbRI_Modelo_RA` existe, com duas linhas** — «Modelo Registro» e «Modelo
> Averbação». As duas têm **820 bytes de cabeçalho RTF e texto nenhum**: são
> modelos em branco. O módulo de modelos do E-Ofício que funciona é o do
> Registro Civil, e é esse que está copiado.

---

## 3. Os claros: 153 — e a contagem errou duas vezes antes disso

No E-Ofício o claro se escreve **`@nomedocampo`**. O texto de cada um dos 13
modelos foi extraído do RTF e varrido: são **153 claros distintos** e **404
ocorrências**.

**A CONTAGEM ERROU DUAS VEZES ANTES DESSE NÚMERO, as duas por defeito da minha
própria ferramenta de medição — e as duas devolveram número plausível.**

> **A primeira deu 186.** O varredor de RTF trocava `\par` por quebra de linha
> **antes** de `\pard`, e o `d` que sobrava grudava na palavra seguinte:
> `@anonascimentodHORA` em vez de `@anonascimento`. **Trinta e um claros que
> não existem.** Palavra de controle do RTF se corta por **fronteira**, e não
> por prefixo.

> **A segunda deu 155**, e essa custou mais que um número. Ela contava
> `@cartorio` e `@gmail` como claros — e os dois são a **cauda dos endereços de
> e-mail do rodapé**: `contato@exemplo.invalid` e
> `conta.google@exemplo.invalid`. Os dois tinham entrado no de-para, e a
> conversão transformaria o e-mail da serventia em `Cidade Exemplo{cartorio}.ch`;
> e `conferir_corpo` recusaria, como «texto do E-Ofício», **qualquer modelo com
> um endereço de e-mail dentro** — isto é, o rodapé da casa.
>
> **O `@` de um claro não vem depois de letra ou dígito.** Hífen e ponto não
> desqualificam: nos modelos reais há `@municipiofalecimento-@uffalecimento`, e
> local de e-mail não termina em hífen.

**A lição das duas é a mesma, e é maior que elas: a medição que erra não avisa
que errou** — ela devolve um número com a mesma cara do número certo. As duas
foram achadas olhando o texto de um modelo real, e não relendo a ferramenta.

E o mesmo claro aparece **com e sem maiúscula**: `@dataatual` e `@dataAtual`,
`@nomenascido` e `@NOMENASCIDO`. Por isso a conversão desta casa compara **em
minúscula**.

---

## 4. O que mudou aqui, e por quê

### 4.1 O claro é `{campo}`, e não `@campo`

Esta casa **já tem** formato de claro, com conferidor e razão escrita
(`modelos_da_casa.CHAVES`): é o do `str.format`, o mesmo dos três termos do
livro. Um segundo formato para a mesma coisa daria **duas conferências para
divergirem**, e quem escrevesse no formato errado descobriria pela recusa, e
não antes dela.

**Para não custar ao oficial os textos que ele já tem**, `traduzir_do_eoficio`
converte um texto colado do E-Ofício.

### 4.2 A conversão não adivinha, e não apaga

O de-para tem **141 entradas**, e cada uma tem os **dois lados medidos**: o
claro do E-Ofício, como aparece nos 13 modelos, e o claro desta casa, que
existe no vocabulário. **Foi essa regra que tirou de lá `@cartorio` e
`@gmail`** quando a medição corrigida mostrou que eles não aparecem uma única
vez nos 13.

**Medido contra os 13 modelos reais: 145 dos 153 claros distintos, e 386 das
404 ocorrências — 96 %.**

O que não está no de-para **continua escrito no texto** e volta numa lista na
tela. As duas alternativas foram recusadas:

- **apagar** faria o oficial descobrir o buraco no papel impresso;
- **adivinhar** poria o dado errado debaixo do rótulo certo, que é o pior lugar
  para um erro num documento de registro civil.

Os **8 que não convertem**, e a razão de cada família:

| claro | por que não |
|---|---|
| `@numerofiliacao1` · `@numerofiliacao2` · `@numerodeclarante1` | é o **número da casa**, e `rc_pessoas` guarda o logradouro inteiro em `endereco` — não há coluna separada |
| `@enderecocomplementofiliacao1` · `…2` | idem, o complemento |
| `@datargdeclarante1` | data de expedição do RG — não há coluna |
| `@observacaoSetencaJudicial` | campo livre do E-Ofício, sem equivalente |
| `@avosnascido` | os quatro avós num campo só; aqui são `{avos_paternos}` e `{avos_maternos}` |

### 4.2.1 A correção que o teste fez, e ela é do desenho

**Eu havia escrito que a filiação dos nubentes não se convertia porque «esta
casa não sabe de quem é cada um», e isso estava errado.** Quem desmentiu foi a
mensagem de recusa de `lavrar_assento` num teste das telas: ela cobra
«filiação 1 do segundo nubente». **Esta casa tem os quatro papéis próprios** —
`PAI_NUBENTE1`, `MAE_NUBENTE1`, `PAI_NUBENTE2`, `MAE_NUBENTE2` — desde
31/08/2026.

O que é verdade, e continua sendo, vale só para o **acervo**: medido em
07/09/2026, os 20 casamentos importados têm **12 `PAI` e 12 `MAE` avulsos**,
que **não dizem de qual nubente são**.

Então a conversão existe, aponta para os quatro papéis próprios, e **não cai
nos avulsos**: num casamento do acervo esses claros saem **vazios**, e vazio
aparece na conferência. Cair no avulso daria os pais de um sob o rótulo do
outro — e o parentesco é aquilo que a certidão de casamento existe para provar.

> **A LIÇÃO É SOBRE A MEDIÇÃO, E NÃO SOBRE O CASAMENTO.** Eu medi o *acervo* —
> `rc_pessoas` na produção — e concluí sobre o *sistema*. **O que a casa
> guardou é o passado; o que ela sabe guardar é outra coisa**, e está no código
> que lavra. Quem pegou foi um teste que lavrou um assento de verdade.

### 4.2.2 O mesmo claro não quer dizer a mesma coisa nas três espécies

`@nomefiliacao1` é o pai do registrado num modelo de **nascimento** e o pai do
**primeiro nubente** num modelo de **casamento** — o E-Ofício numera de 1 a 4
ali, dois para cada nubente. Por isso há uma camada por espécie
(`DE_PARA_POR_ESPECIE`) sobre o de-para geral.

**Quem achou isto foi a prova dos 13 modelos reais, e não a releitura.** Doze
convertiam e passavam na conferência; o nono — «Comunicação de Casamento para o
Registro de Nascimento» — produzia `{pai_nome}`, que **não existe no
vocabulário do casamento**. O oficial receberia «converti 13 claros» seguido de
«não sei preencher {pai_nome}», na mesma tela.

### 4.2.3 A prova: os 13 modelos, de ponta a ponta

Cada um dos 13 modelos reais foi extraído do RTF, convertido e submetido à
mesma `conferir_corpo` que a tela usa para gravar:

| | |
|---|---|
| convertem e **passam na conferência** | **13 de 13** |
| claros convertidos, somados | **367** |
| claros que ficaram escritos com `@` | **18**, e todos aparecem na lista |

**É a diferença entre «o de-para tem 141 entradas» e «os modelos do oficial
funcionam».** A primeira frase é sobre a tabela; a segunda é sobre o trabalho
dele, e só a segunda se pode prometer.

### 4.3 O claro sem dado aparece **antes** de imprimir

No E-Ofício o claro sem dado vira **espaço em branco no papel**, e quem
descobre é quem lê o documento depois de assinado. Aqui `montar` devolve o
texto **e a lista dos claros que saíram vazios**, com o rótulo de cada um, e a
tela a mostra numa faixa que não sai na impressão.

É o **«conferir e imprimir são dois botões»**, pela sexta vez neste projeto.

---

## 5. De onde sai cada valor — e a armadilha que isso tem

**A coluna do assento vem primeiro; o blob do acervo é o recurso.** É a regra
que `rc_certidao._de` já paga desde 28/08/2026, e aqui ela é ainda mais
necessária.

Medido na produção em 07/09/2026, só leitura:

| | |
|---|---|
| assentos | **244** — e **todos são do acervo** (`bitAcervo = 1` nos 244) |
| `hora_fato` · `cor_raca` · `causa_morte` · `local_sepultamento` · `atestante` · `titulo_eleitor` · `cpf_registrado` · e mais treze | **0 de 244** |
| o valor delas | está em `dados_json`, **com o nome da coluna do E-Ofício** — `strHoraNascimento` (192/192), `strCausaMorte` (31/31), `strLocalSepultamento` (15/31)… |

**Um vocabulário que lesse só as colunas próprias funcionaria perfeitamente em
todo ato novo e devolveria documento em branco para o acervo inteiro** — que é
justamente o que se certifica todo dia. E o contrário também: se o blob
ganhasse, o escrevente corrigiria a hora na tela e continuaria imprimindo a
antiga.

### O vocabulário desta casa

| espécie | claros |
|---|---|
| nascimento | **127** |
| casamento | **161** — são seis pessoas: os dois nubentes e as quatro filiações |
| óbito | **127** |
| **distintos ao todo** | **309** |

Cada claro declara **de onde sai**, e há teste que exige isso de todos: é o que
impede um claro adivinhado de entrar na lista.

Os **avós têm só o nome**, e é medido: nas 631 linhas de avô/avó da produção,
todas as colunas de qualificação estão vazias — o E-Ofício guardava só o nome
deles (`tbProgenitor`). Oferecer «profissão do avô materno» seria oferecer um
claro que sai vazio em 100 % dos casos.

---

## 6. O que este módulo não faz

**Não lavra ato, e não é o termo do livro.** O termo tem lugar próprio
(`rc_modelos_do_livro`), é montado dos requisitos da Lei nº 6.015/1973, do
Código Nacional de Normas e do Código de Normas do TJMA, e foi decisão do
oficial em 30/08/2026 que ele **não** saísse dos modelos do E-Ofício — «não
utilizaremos os modelos ruins do e-ofício, nem em papel».

**Isto aqui é o outro lado, e é o que aqueles 13 eram**: os papéis avulsos.

**Não seleciona nem numera.** Documento avulso não é ato; se um dia algum
destes papéis passar a ser ato selado, quem sela é o módulo do selo.

**A espécie não muda depois de gravada.** Trocá-la trocaria o vocabulário
debaixo do texto — os claros de óbito viram desconhecidos num modelo de
nascimento, e o documento sairia com buraco.

**Desativar não é apagar.** O modelo que já imprimiu documento é a forma do que
a casa assinou; apagá-lo tiraria da serventia a explicação do papel que está na
mão do cidadão.

---

## 7. Onde isso mora

| arquivo | o que é |
|---|---|
| `rc_modelos_livres_schema.py` | a tabela `rc_modelos_livres` e as três espécies |
| `rc_modelos_livres.py` | o vocabulário, a conferência, `montar` e o de-para do E-Ofício |
| `rc_modelos_livres_web.py` | as cinco rotas — `rcpn_*`, que é o que põe a tela no Registro Civil |
| `templates/rcpn_modelos.html` | a lista, o filtro e o cadastro |
| `templates/rcpn_modelo.html` | o editor, a lista de claros e a conversão |
| `templates/rcpn_modelo_documento.html` | o documento montado, com a faixa dos claros vazios |
| `tests/test_rc_modelos_livres.py` | **55** testes de domínio |
| `tests/test_rc_modelos_livres_web.py` | **28** testes das telas |

**No menu:** Registro Civil → O balcão → **Modelos de documentos**.

---

## 8. O que não se mediu

**O texto dos 13 não foi importado.** Eles são os «modelos ruins» de que o
oficial falou em 30/08/2026, e três deles são certidão — que esta casa já emite
pelo modelo do CNJ (Prov. 182/2024), com quadro próprio. O que se copiou foi o
**módulo**; o que entra nele é o que a casa escrever.

**A tela do E-Ofício não foi vista.** O que se mediu foi a **tabela** — o que
ela guarda e o que ela nunca guardou. Nada se afirma aqui sobre os botões
daquela tela.

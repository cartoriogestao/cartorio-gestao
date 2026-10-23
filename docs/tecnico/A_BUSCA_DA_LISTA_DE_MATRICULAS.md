# A busca da lista de matrículas — o que se mediu, e o que foi decidido

**Relato #55, de 14/09/2026, às 09h59, pela escrevente:**
*«verificar porque pesquisando a matricula 3110 encontrou a 3602 somente»*

Fui medir contra o banco da serventia. **A inconsistência é real, e são três** — uma
delas não tem nada a ver com matrícula, e as outras duas já estavam lá antes de
alguém reparar nelas.

> **DECIDIDO EM 15/09/2026, E FEITO NO MESMO DIA:** documento **exato**, número
> **exato**, nome **normalizado**. As seções 1 e 2 são a medição que motivou a
> pergunta; a 3 é a resposta; a 6 é o que entrou, com os números de antes e de
> depois. A leitura das seções 3 a 5 é registro do processo — **o que vale hoje é a
> seção 6.**

---

## 1. O que a caixa de busca fazia antes da decisão

Ela é **uma caixa só**, e procura em **cinco lugares ao mesmo tempo**, sempre pelo
critério «contém» (`%texto%`):

| onde procura | o campo |
|---|---|
| o número da matrícula | `ri_matriculas.numero` |
| o Código Nacional de Matrícula | `ri_matriculas.cnm` |
| o endereço do imóvel | `ri_matriculas.logradouro` |
| o **nome** das partes | `ri_partes.nome` |
| o **documento** das partes | `ri_partes.documento_numero` |

Isso explica o relato inteiro: **a 3602 apareceu por causa de um CPF.**

## 2. O que eu medi

### A 3602

A parte **PESSOA EXEMPLO** tem documento **00000000191**. Os quatro
dígitos **3110** estão *dentro* dele. Como a comparação é «contém», a matrícula dela
entra na lista de quem procura por 3110.

**Não existem duas matrículas 3110.** Existe uma pessoa cujo CPF tem esses quatro
dígitos.

### O tamanho do ruído, em números do acervo de vocês

| o que se digita na caixa | o que ela achava | o que acha pelo número exato |
|---|---|---|
| `3110` | **2** matrículas (a 3110 e a 3602) | **1** — a 3110 |
| `314` | **7** | **1** — a 314 |
| `1` | **1.198** | **1** — a 1 |

A linha do `1` não é exagero de teste: é o que a tela mostrava se alguém digitasse
`1` e apertasse buscar. Mil cento e noventa e oito fichas entravam por causa de um
dígito dentro de um CNM, de um endereço, de um nome ou de um documento.

> **Os números desta tabela são a MEDIÇÃO QUE MOTIVOU a pergunta** — o «pelo número
> exato» é a projeção de então. O que a tela faz hoje, com a decisão tomada e o
> código no lugar, está na **seção 6**.

### O documento, medido

- partes cujo documento **contém** `3110`: **1** (a da 3602);
- partes cujo documento **é** `3110`: **0**.

Ou seja: **comparar o documento inteiro não tira ninguém** de uma busca que hoje
funcione. O que ele tira é o ruído.

### O nome — e este é um defeito que eu não sabia que existia

A busca do nome, nesta tela, compara o texto **cru**, com maiúsculas e acentos como
estão gravados. A tela vizinha — *Indicador Pessoal* — já compara pelo nome
normalizado. **São duas réguas na mesma família de telas:**

| quem digita | achava antes | acha agora |
|---|---|---|
| `PESSOA EXEMPLO` | 2 | 2 |
| `Pessoa Exemplo` | **0** | **1** — a ficha 977 |
| `Pessoa Exemplo` | **0** | **1** — a ficha 1237 |

**1.631 das 3.992 partes (41%) só se acham pelo nome normalizado** — 1.257 têm
acento no nome e 622 têm minúscula. Quem digita o nome como se fala — em minúsculas
— **não achava ninguém**. E o acervo tem 2.820 partes sem documento (71%), de modo
que o nome é, para a maioria, o único caminho até a ficha.

> **«557 nomes com acento» foi a minha primeira medição, e estava errada.** O número
> conferido — por três definições, em 15/09/2026 — é **1.257 com acento** e **1.631
> exigindo alguma normalização**. Fica registrado porque o número errado chegou a
> ser escrito: contagem feita com a régua errada tem a mesma cara da certa.

## 3. A pergunta era sua, e a resposta foi esta

**Documento: EXATO. Número: EXATO. Nome: normalizado.** (15/09/2026)

| | o que acontece agora |
|---|---|
| **Exata** ← escolhido | quem digita o CPF inteiro acha — com ou sem máscara —; quem digita quatro dígitos soltos deixa de achar o registro de outra pessoa |
| «Contém» | era como estava: qualquer trecho do CPF trazia a ficha, inclusive por engano |

A consequência estava medida dos dois lados: **a exata não tira ninguém** de uma busca
que desse certo, porque não existe documento igual a `3110` em parte nenhuma do
acervo. Ela só tira o que entrou por acidente.

E a segunda decisão, na mesma linha: **o número da matrícula também é exato agora** —
era de onde saíam as 1.198 fichas do `1` e as 7 do `314`. Número de matrícula não tem
«parecido»: ou é aquela ficha, ou não é. **O endereço e o nome continuam por trecho**,
que é como se procura um imóvel e uma pessoa.

## 4. O que não era pergunta, porque só acrescenta

**A busca por nome passou a ser normalizada** — sem acento e sem diferença de
maiúscula. O motivo é medido: ela **só adiciona** achados. Ninguém deixa de achar o
que achava; quem digitava o nome em minúsculas passou a achar.

## 5. O que já está feito neste relato

A 3110 estava com as colunas de busca por livro **em branco**, e a 3602 não — por
isso, com o filtro por livro ligado, era ela que sumia. Isso foi consertado:

- a importação passou a **derivar** essas colunas em vez de esperar que o arquivo as
  traga;
- há uma passada (`preencher_colunas_derivadas`) que as preenche no que já foi
  importado, e ela **roda sozinha na subida do sistema**, ao lado das migrações.

Medido contra cópia da produção: `ri_matriculas.livro_norm` vazias **1 → 0**;
`ri_partes.nome_norm` **6 → 0**. As 277 fichas que continuam sem `imovel_norm` não
têm perímetro escrito — a passada não inventa valor onde não há fonte.

## 6. O que entrou, com os números de antes e de depois

Medido na produção, só leitura, com as duas condições lado a lado — a de antes, como
está no `.cgu` da 3.6.130, e a de agora, tirada de `ri_web._condicao_de_busca_da_matricula`:

| o que se digita | antes | depois |
|---|---|---|
| `3110` | 2 | **1** — a 3110, e a 3602 saiu de vez |
| `314` | 7 | **1** — a 314 |
| `1` | 1.198 | **3** |
| `067` | 116 | **1** |
| `4013` | 1 | 1 |
| `PESSOA EXEMPLO` (sem acento) | **0** | **1** |
| `Pessoa Exemplo` (minúscula) | **0** | **1** |
| `000.000.001-91` (CPF com máscara) | **0** | **1** |
| `00000000191` (CPF sem máscara) | 1 | 1 |
| `000000.2.0003236-93` e `0000002000323693` (CNM) | 1 e 1 | 1 e 1 |

**Por que a busca por `1` ainda devolve três, e não uma:** são a ficha **1**, que é o
número exato, e as fichas **529** e **3.521** — que entram porque o **nome** de uma
parte delas contém `1` (`1ª PESSOA EXEMPLO` e `3521`). Nome é texto, e
texto se procura por trecho; é a mesma sujeira de acervo que o ONR mostrou — sete
nomes que começam com sinal ou dígito, em 3.992.

### O que mudou no código

- **A regra mora num lugar só:** `_condicao_de_busca_da_matricula()`, em `ri_web.py`,
  usada pelas **três** telas que procuram — a lista de matrículas, o indicador real e
  o indicador pessoal. Quatro réguas, e o que decide qual vale é o que se digita:
  número e CNM por igualdade; documento por igualdade quando o que se digitou tem
  dígitos suficientes para ser documento; nome e endereço por trecho, na coluna
  normalizada.
- **O CNM se acha com e sem máscara**, e o documento também: tira-se o que não é
  dígito dos dois lados antes de comparar.
- **A parte cadastrada pelo balcão passou a nascer pesquisável:** o `INSERT` de
  `ri_partes` não gravava `nome_norm`, de modo que toda parte nova ficava invisível
  para a busca por nome — a coluna existia e só o acervo importado a tinha.
- **A passada das colunas derivadas roda na subida do sistema**, ao lado das
  migrações (`preencher_colunas_derivadas`), e é idempotente: rodada duas vezes, não
  move nada. A importação também passou a derivar em vez de esperar que o arquivo as
  traga.

### As provas

`tests/test_busca_da_lista_de_matriculas.py` — **doze testes**, e eles **medem** o
defeito: conferidos contra a regra de antes, **sete ficam vermelhos** («3110»
devolvia `[3110, 3602]`, «314» devolvia `[314, 3140]`, o CPF com máscara devolvia
vazio, o nome em minúscula devolvia vazio). A do `nome_norm` fica vermelha quando se
desfaz a derivação. **Teste que passa dos dois lados não prova nada.**

A passada das colunas tem mais **cinco** em `tests/test_importar_padrao.py`,
incluindo a que exige que a subida do banco a chame.

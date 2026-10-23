# A remessa do IBGE, gerada e conferida contra a que esta casa mandou

*28/08/2026 — Serventia Extrajudicial de Cidade Exemplo/MA, CNS 000000*

Este documento fecha um trabalho que começou em 27/08 sabendo só o **layout** do
arquivo e terminou gerando-o, com cada linha conferida contra a que o E-Ofício
exportou de verdade.

---

## O que faltava, e não era o layout

O layout estava fechado desde 27/08. O arquivo continuava impossível por uma
razão simples e que não aparecia lendo a especificação:

> **`rc_pessoas` guardava pai, mãe e avós — e não guardava a pessoa de quem o
> assento é.**

A carga trouxera a filiação porque a **certidão de nascimento** a cobrou. O
registrado, os dois nubentes e o falecido tinham só o **nome**, em
`rc_assentos.nome`, e mais nada: nem sexo, nem data de nascimento, nem
naturalidade, nem residência, nem estado civil.

E isso travava duas coisas ao mesmo tempo — por isso foi uma passada só:

- a **remessa do IBGE**, que pede exatamente esses cinco campos;
- a **certidão de casamento e a de óbito**, que descrevem essas mesmas pessoas.

### O acervo tinha tudo

| espécie | o que o acervo traz |
|---|---|
| nascimento | 193/193 com sexo e data de nascimento, e com UF e cidade |
| casamento | 20/20 com sexo, data, estado civil e **nome pós-casamento** dos dois cônjuges |
| óbito | 31/31 com sexo, data, estado civil, naturalidade e residência |

Entraram **264 pessoas**: 193 registrados, 20 + 20 nubentes, 31 falecidos.

**O nome de casada não é enfeite**: medido, o segundo cônjuge muda de nome em
**17 dos 20** casamentos, e o primeiro em 2. É o nome que a certidão mostra, e
guardar só um dos dois perderia o outro.

---

## Três defeitos que o ensaio contra o acervo achou, e os testes de regra não

### 1. A chave era do assento, e não da pessoa

`rc_pessoas` tem `UNIQUE(origem, origem_chave)`, e **os dois nubentes moram na
mesma linha do acervo**. Com a chave do assento, o NUBENTE1 entrava e o NUBENTE2
era ignorado em silêncio pelo `INSERT OR IGNORE`.

### 2. O contador contava tentativa, e não entrada

**A carga dizia «entraram 20» e a tabela tinha zero.** Foi o contador errado que
tornou o defeito acima visível — se ele contasse certo teria dito zero e eu teria
procurado; dizendo 20, ele confirmava o engano.

> É a regra da casa outra vez: contar pelo `lastrowid` mudar, e nunca pelo
> número de linhas que se tentou gravar.

### 3. Vinte e uma pessoas «nascem» depois do próprio ato

Medido: **7 dos 20 casamentos em cada cônjuge, 6 dos 193 nascimentos e 1 dos 31
óbitos**. O valor guardado não é a data de nascimento — é o dia em que alguém
digitou o registro antigo, com o campo em branco pegando a data de hoje.

**Não entram, e não se consertam por palpite.** O assento fica sem data e a
carga avisa com o número, para quem for à estante saber a quais ir. Certidão com
data falsa e IBGE com idade absurda são os dois piores que o campo vazio: campo
vazio não afirma nada.

E a mesma recusa vale no balcão: quem digitar data posterior ao ato recebe a
frase antes de o assento existir, com o cliente ainda na frente.

---

## O ensaio de verdade: gerar e comparar

Peguei os cinco arquivos que o E-Ofício exportou em `C:\ARPNET\C11\IBGE_EXP`,
gerei o **segundo trimestre de 2026** a partir do acervo, e comparei posição por
posição.

| arquivo | linhas geradas | linhas reais | idênticas |
|---|---|---|---|
| `CARTINF02.TXT` (casamento) | 2 | 2 | **2 — byte a byte** |
| `CARTINF03.TXT` (óbito) | 13 | 13 | **8** |
| `CARTINF01.TXT` (nascimento) | 28 | 28 | 0, e só por dois campos |

O casamento sair idêntico prova o montador inteiro: cabeçalho, trimestre, número
do livro, datas invertidas, sexo, estado civil pelo catálogo certo e os seis
códigos de município e país dos dois cônjuges.

### O que a comparação corrigiu no sistema novo

**O número do livro tem forma própria no arquivo.** O real escreve `A24`, `B04`,
`C05` — letra colada ao número, dois dígitos, **sem hífen**. O sistema guarda
`A-24`, que é como o livro de papel se chama e como a certidão o imprime. Quem
tem forma própria é o arquivo, e a conversão mora nele.

**O de-para do local do nascimento estava no próprio acervo.** O E-Ofício numera
de 1 a 5 e o IBGE **não tem 4** — pula do 3 para o 5. A tradução está em
`tbRCPN_LocalNascimento.intCodigoIBGE`, dizendo que o `4` de lá é o `5` daqui.

**A natureza do óbito também estava**, e eu havia escrito no código que não. A
coluna se chama `strTipoMorte`: «Natural» em 27 e «Violenta» em 4, e o de-para
fecha em **13 de 13** contra o arquivo exportado.

> **Quarta vez neste projeto.** Antes foram o `codigoAto` dentro do `memJson`,
> os dois contadores do RCPN em `tbPropriedadeRCPN`, e o de-para do local do
> nascimento. **Não achar a coluna que procurei não prova que o dado não existe
> — prova que procurei pelo nome errado.**

---

## Três defeitos do E-Ofício, que a comparação achou e que ninguém veria de outro jeito

### 1. A idade dos falecidos ia um ano a mais

Quem nasceu em **12/07/1928** e morreu em **06/04/2026** tinha 97 anos. O arquivo
que esta casa mandou diz **98**.

A conta era `ano do óbito − ano do nascimento`, sem descontar o aniversário que
ainda não tinha chegado. Medido: **3 dos 11 óbitos comparáveis**, cerca de 27%.

### 2. A residência da mãe era o município do parto — e este é o mais caro

Medido: em **27 das 28** linhas de nascimento, o `COD-MUNIC-RES-MAE` é **igual**
ao `COD-MUNIC-NASC`.

Mãe que mora em Cidade Exemplo e teve o filho no hospital de Imperatriz ia para o
IBGE como **moradora de Imperatriz**. E é por município de residência que o IBGE
distribui a estatística de natalidade — que é o número usado para dimensionar
saúde, creche e escola.

O sistema novo tira a residência da **mãe**, em `rc_pessoas`, e não do lugar
onde a criança nasceu. Há teste que recusa se a fonte voltar a ser o parto.

### 3. Duas das treze linhas de óbito estão truncadas

102 posições em vez de 103. Falta um caractere **no meio**, e tudo depois dele
anda uma casa para a esquerda: a UF de nascimento sai `10` e o país `763`, que
não existem em tabela nenhuma. O IBGE aceitou.

As linhas geradas têm 103, e há teste de largura que garante isso nas três
espécies.

---

## O que ainda difere, e por que fica assim

**`IDADE-GENI` e `COD-*-RES-MAE`.** O arquivo antigo não os tira do acervo: a mãe
de `tbFiliacao` mora em Cidade Exemplo e o arquivo diz Imperatriz; a data de
nascimento dela dá 29 anos e o arquivo diz 27 — e há linhas com `01`, que seria
uma mãe de um ano.

**Os nossos são rastreáveis; os dele não.** Não se persegue igualdade com um
número que não se sabe de onde veio.

---

## O que ainda falta

**A tela que gera o arquivo.** `montar()` está pronto e testado; falta o botão
que escolhe ano e trimestre, mostra a conferência e baixa o `.zip`. É a sexta vez
neste projeto que a mesma pergunta acha o mesmo tipo de buraco — função de
domínio pronta que nenhuma tela chama —, e desta vez ela foi feita antes de o
buraco ficar velho.

**A natureza do óbito no balcão.** A carga a traz do acervo; o ato **novo** ainda
depende de o escrevente marcá-la na tela, que já tem o campo. Sem ela, a linha
sai com `9` (ignorado), que é o que o IBGE manda usar — mas ignorado demais é
remessa aceita e inútil.

**A conferência mede isso**, e é por isso que ela existe: `conferir()` conta
quantas posições saíram como «ignorado» e diz de quais campos. Remessa cheia de
nove é aceita pelo IBGE e não serve para nada — e quem manda precisa saber a
diferença antes de mandar.

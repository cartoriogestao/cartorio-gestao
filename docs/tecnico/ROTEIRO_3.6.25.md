# Roteiro da 3.6.25 — pai e mãe trocados, e a certidão que saía em branco

*Serventia Extrajudicial de Cidade Exemplo/MA, CNS 000000 — 28/08/2026*

**2.424 testes, todos passando.** O pacote é `CartorioGestao_3.6.25.cgu`,
SHA-256 `eee3b111ba2bb4a280aaf8c67d9a84d457787c846365b4a2c82fcbbf33f2c931`.

> **Ela inclui tudo o que estava na 3.6.23 e na 3.6.24.** Aplique só esta.

---

## O defeito mais sério desta série, e ele saía no papel assinado

### Em 42 assentos, a mãe estava gravada no lugar do pai

O sistema traduzia o código do E-Ofício assim: **1 é o pai, 2 é a mãe**. Eu tinha
escrito isso com um comentário dizendo que era medido — e o que se mediu foram
os **pares** (dois por registro em 196 de 196), **não quem é quem dentro do
par**.

Medindo o acervo inteiro agora:

| | código 1 | código 2 |
|---|---|---|
| nascimento | 162 homens, **30 mulheres** | 158 mulheres, 18 homens |
| óbito | 19 homens, **12 mulheres** | 20 mulheres, 8 homens |

E há o caso que não deixa dúvida: `(1, Feminino, PESSOA EXEMPLO)` com
`(2, Masculino, PESSOA EXEMPLO)` — os dois com nome, e simplesmente
trocados.

**Quarenta e duas certidões sairiam com a mãe no lugar do pai.** E a remessa do
IBGE usa a mãe para a residência e para a idade da genitora — com a pessoa
errada.

Agora **o sexo decide**, e o código do E-Ofício só desempata quando o sexo falta.

### E o casamento tem quatro filiações — o sistema lia duas

Os códigos **1 e 2 são os pais do primeiro cônjuge**, e **3 e 4 os do segundo**.
Conferido pelos sobrenomes, que casam um a um.

Lendo só os dois primeiros, **23 pessoas nunca entravam** — e a certidão de
casamento mostrava uma filiação só, **como se fosse «a» filiação**. Quem lesse
concluiria que aqueles eram os pais dos dois.

### Uma correção minha, meia hora depois da primeira

A regra «o sexo decide», olhando cada linha sozinha, conserta os 42 — e **cria um
problema pior num caso**: no registro 19532 o acervo marca **as duas pessoas
como «Masculino»** (uma delas é Pessoa Exemplo; o sexo é que está errado ali). Saíam
**dois pais e nenhuma mãe**, e a mãe sumia da certidão e do IBGE.

A regra certa é **por par**: um assento tem um pai e uma mãe, e essa invariante é
mais forte que qualquer um dos dois sinais. Quando os sexos se contradizem, eles
decidem; quando dizem a mesma coisa, o código desempata — **e vira aviso**,
porque um dos dois está errado no acervo e alguém precisa conferir no livro.

> Quem pegou isto foi o teste que compara a remessa com o arquivo que você
> mandou ao IBGE: ele acusou uma diferença nova, fui medir, e o caso apareceu.

---

## A certidão de casamento e a de óbito saíam em branco

Não nas do acervo — nas de **qualquer ato que esta casa lavrasse a partir de
agora**.

Elas liam do bloco de dados do E-Ofício (`strNomeConjuge1`, `strEstadoCivil`),
que só existe nos 244 assentos importados. Num casamento novo, o campo
**«NOME QUE CADA CÔNJUGE PASSOU A UTILIZAR»** — que é o motivo pelo qual a
certidão de casamento existe, porque é ele que prova a mudança de nome — saía
`ND`.

Agora as duas leem das **pessoas do assento**, e mostram:

- de cada cônjuge: data de nascimento, naturalidade, estado civil anterior,
  profissão e **a filiação dele**;
- do falecido: sexo por extenso, **idade calculada** (descontando o aniversário
  que não chegou), data de nascimento, estado civil, profissão, naturalidade e
  último domicílio.

## O regime de bens não existia em campo nenhum

É campo obrigatório da certidão de casamento — Lei 6.015/1973, art. 70, item 6 —
e só existia dentro do bloco do acervo. Agora é escolha na tela de lavrar.

Ele é **diferente** do regime da habilitação, e por isso tem campo próprio: o
casal pode mudar de regime entre a habilitação e a celebração, e o que vale na
certidão é o que o assento afirma.

---

## Os passos

**1. Feche o sistema.** **2. Faça o backup.** **3. Aplique o `.cgu`.**
**4. Confira que `VERSAO.txt` diz 3.6.25.**

**5. Rode a carga do acervo**, marcando **tudo**. Confira:

| | |
|---|---|
| assentos do RCPN | **244** |
| registrados / nubentes / falecidos | **193 / 20 + 20 / 31** |
| pais e mães | **209 pais e 222 mães**, e **12+12+12+12** dos cônjuges |
| municípios do IBGE | **5.570** inseridos, **68** rejeitados |
| avisos | **30** — datas impossíveis, sexo repetido e o Livro E |

**6. Abra uma certidão de casamento do acervo** e confira que ela mostra a
filiação de **cada** cônjuge, e não uma só.

---

## O que fica para depois

**Os 7 assentos em que o acervo diz que pai e mãe são do mesmo sexo.** Eles estão
nos avisos da carga, com o número. Quem for à estante confere no livro de papel —
e, se estiver trocado, a correção é uma retificação, não uma edição.

**As outras remessas do Registro Civil**: SIRC, CRC e DNV.

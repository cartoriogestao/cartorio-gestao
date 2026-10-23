# A certidão do Registro Civil, medida antes de ser construída

Feita em **26/08/2026**, na "passada própria" que você decidiu em 25/08 — as
certidões do Protesto e do RCPJ/RTD primeiro, e esta separada.

**O motivo da separação está no dado.** Os 244 assentos do acervo **não têm
teor nenhum**: as três colunas de texto estão vazias nas três tabelas de
origem. No RCPJ/RTD a certidão *reproduz* o livro; aqui ela se **monta dos
campos**. São coisas diferentes, e enfiá-las no mesmo módulo teria dado um
módulo com dois corpos.

---

## O modelo é medido, e não inventado

`tbCertidaoRCPN` guarda **145 certidões reais desta casa, com o texto
inteiro** — 126 de nascimento, 18 de casamento e 3 de óbito. Os rótulos, a
ordem dos blocos e o que vai em cada um saíram delas.

É a mesma disciplina das 65 do Protesto e das 44 do RCPJ/RTD: **o papel que
esta casa entrega é o que ela já entregava.**

A ordem dos blocos não é enfeite — é a ordem em que quem lê a certidão procura
as coisas. Mudá-la faria o escrevente conferir na diagonal.

---

## O que a certidão cobrou da carga — pela **terceira e quarta** vez

Este projeto tem um padrão que já se repetiu quatro vezes: **é a certidão que
descobre o que a carga não trouxe.**

| Quando | O que faltava | Onde estava |
|---|---|---|
| 25/08 | o **devedor** do Protesto | `tbPessoa`, nunca aberta |
| 25/08 | o **ato de registro** do RCPJ/RTD | dava certidão sem livro nem folha |
| **26/08** | **os pais e os avós** do RCPN | `tbFiliacao` e `tbProgenitor`, nunca abertas |
| **26/08** | **o ato de registro** do RCPN | a certidão imprimia `LIVRO ND` |

### Os pais e os avós

- **`tbFiliacao` são os pais** — 2 por registro em 196 de 196 —, e serve as
  três espécies: 392 de nascimento, 48 de casamento, 62 de óbito.
- **`tbProgenitor` são os avós**, e só de nascimento: as 784 linhas têm
  `intTipoRegistro = 1`. A filiação 1 são os **paternos** e a 2 os **maternos**;
  o sexo separa avô de avó.

Contra o acervo real: **1.084 pessoas** — 235 pais, 218 mães, 175 avós paternas,
157 avôs paternos, 157 avós maternas, 142 avôs maternos. **Nove assentos ficam
sem filiação**, e eles são casamentos: dos 193 nascimentos, **todos os 193 têm
filiação no acervo**.

> **Sem filiação não há certidão de nascimento.** Ela é o corpo da certidão, e
> não um campo a mais. O módulo recusa dizendo que o assento **existe no livro**
> e que o que falta é trazer a filiação.

### O ato de registro

O livro e a folha **moram no ato**, e não no assento — quem ocupa face do livro
é o ato. A carga do RCPN nunca lavrou o ato de REGISTRO, e por isso a certidão
imprimia `LIVRO ND / FOLHA ND`: **papel que não diz de onde foi tirado.**

`intFolha` está preenchida em 193/193 nascimentos, 20/20 casamentos e 31/31
óbitos. A letra do livro só sai de onde foi medida: no nascimento é
`strTipoLivro` (`A` em 192, `E` em 1); no casamento e no óbito **o acervo não
tem coluna com a letra**, e ali sai só o número.

---

## Os quatro defeitos que só o ensaio contra o acervo real achou

Os 31 testes de domínio passavam. Nenhum deles via nada disto, e por um motivo
só: **nos testes o assento entra com os campos preenchidos do jeito certo, e o
acervo não é assim.** Foi imprimir a certidão de uma pessoa de verdade que
mostrou.

### 1. A certidão dizia que o registro foi feito **hoje** — o pior deles

Eu havia usado, no campo `DATA DO REGISTRO POR EXTENSO`, a data que a tela passa
— que é a data da **emissão**. A certidão de um casamento de 1957 saía dizendo
que o registro é de **vinte e seis de agosto de dois mil e vinte e seis**.

Uma afirmação **falsa**, no documento mais definitivo que esta casa emite, sem
erro em lugar nenhum.

### 2. `POR EXTENSO` com a data em algarismos

O rótulo prometia uma coisa e a linha entregava `2022-04-06`. As 145 certidões
reais escrevem o dia e o ano inteiros em palavras — *"VINTE E OITO DE MAIO DE
MIL NOVECENTOS E OITENTA E SETE"* —, com o dia 1 virando **PRIMEIRO**. A função
que faz isso já existia na casa (`livro_nucleo.por_extenso`, dos termos de
livro) e bastou usá-la.

### 3. `LIVRO ND / FOLHA ND`

O ato de registro que faltava na carga, acima.

### 4. `IMPERATRIZ/MA./MA`

Algumas cidades do acervo já vêm com o estado dentro. Somar a UF de novo dobrava
o estado. **Não se conserta o dado do acervo** — ele é o que a casa escreveu, e
a certidão reproduz; o que se conserta é não acrescentar o que já está lá.

> **A lição**: teste de domínio prova a regra; **ensaio contra o acervo prova o
> dado**. Os dois são necessários, e o segundo achou o que o primeiro não tinha
> como ver.

---

## O quinto defeito: a certidão **sumia** quando alguém digitava o selo

Este não veio do ensaio, e sim de escrever o teste que faltava.

`rc_certidoes` **não estava registrada** em `ato_selado.TABELAS_DE_ATO`. Sem
ela, `registrar_selo_obtido_a_mao` recusava com *"não é tabela de ato"* — e a
rota, fazendo exatamente o que a casa manda (**selo recusado derruba o
lançamento inteiro**), desfazia a transação.

O resultado no balcão: o escrevente emitia a certidão, digitava o selo, via um
aviso vermelho — **e a certidão não existia mais**.

**Os dezoito primeiros testes de tela passavam**, e todos pelo mesmo motivo:
nenhum digitava selo.

E havia um segundo erro na mesma linha, calado de outro jeito: eu escrevi
`"rcpn"` minúsculo onde as outras nove chamadas da casa escrevem `"RCPN"`. O
razão `sd_selos` ficaria com **duas grafias da mesma atribuição**, e quem
filtrasse por ela veria metade dos selos — meses depois, na conferência.

### O teste que agora guarda os dois

Não é um teste da certidão: é um teste do **conjunto**. Ele lê o código das
telas, junta toda tabela em que alguma delas manda selar ou cobrar, e confere
que todas estão registradas.

**Com piso**: ele exige achar pelo menos sete tabelas. Varredor que deixa de
achar passa calado, e teste que não olha nada é pior que teste nenhum — ele dá
a impressão de que alguém conferiu.

> **A lição**: uma tabela não registrada **não dá erro de programação — dá ato
> perdido**. E o caminho que a produz é o caminho *correto* (desfazer tudo
> quando o selo é recusado) aplicado a uma premissa errada.

---

## A matrícula de 32 dígitos **sai como está**

A estrutura está medida:

```
000000 01 55 1997 1 00011 127 0010385 79
  CNS  ac sv  ano t livro  fl   termo  DV
```

CNS (6) + acervo (2) + serviço (2) + ano (4) + tipo de livro (1) + livro (5) +
folha (3) + termo (7) + verificador (2).

**O verificador não se explica.** Testado contra 243 matrículas reais: módulo 11
com pesos 2..9, 2..7, 32..3 e 2..31, nas duas convenções e com os dez
mapeamentos de resto; módulo 97 / ISO 7064; Luhn. O melhor resultado acertou
**46 de 243** — nível de acaso.

Por isso o sistema **não gera matrícula**, e há teste que fica vermelho se
alguém acrescentar uma função que a gere. Dígito chutado no documento mais
definitivo desta casa volta como erro em cartório de outro estado, anos depois.

---

## Uma pergunta nova para você: o Livro B-Auxiliar

Construir a certidão achou isto, e virou pendência na aba **O que falta
informar**.

O acervo separa os casamentos em dois grupos, por uma coluna chamada
`intTipoRegistroLivro`, e não diz o que ela significa:

| Grupo | Quantos | Livros | Registros |
|---|---|---|---|
| `0` | 17 | 1, 2, 01, 02, 03, 04, 6 | 111 a 1.011 |
| **`1`** | **3** | **1** | **26 a 59** |

O segundo grupo tem **numeração própria em livro próprio** — que é exatamente o
que distingue o **B-Auxiliar** (casamento religioso com efeito civil) do B.

**Mas são três casos, e três casos não provam uma regra.** Podem ser os
primeiros de um livro que mal começou, ou um cadastro usado para outra coisa.
Mandá-los para o B-Auxiliar por conta própria poria assento em livro errado — e
assento em livro errado é o que a inspeção acha primeiro.

Vale aqui a sua regra de 24/08/2026: **onde não há padrão anterior a imitar, o
sistema recusa e pergunta.**

### E você respondeu, em duas partes

> *"Não tivemos casamentos no livro B-Auxiliar nos últimos anos."*

Isso resolveu **a urgência**: se não entra casamento religioso há anos, o
contador que falta no B-Auxiliar não segura nenhum ato próximo.

Não resolveu **o que são os três**, e a medição mostra por quê — eles são de
**1979, 1982 e 1987**:

| Registro | Livro | Folha | Registrado em |
|---|---|---|---|
| 26 | 1 | 13 | 28/12/1979 |
| 44 | 1 | 23 | 17/11/1982 |
| 59 | 1 | 30 | 04/08/1987 |

"Últimos anos" não alcança nenhum deles. Então a pergunta mudou de forma em vez
de ser fechada: deixou de ser *"esses casamentos foram religiosos?"* — que
ninguém sabe de cabeça sobre 1979 — e passou a ser **"o livro de papel diz?"**,
com o endereço de cada um para levar até a estante.

> *"Deixe como o E-Ofício guardou, pendente de confirmação quando forem
> consultados efetivamente."*

**A frase tem duas metades, e a segunda é a que virou código.** Deixar como está
não precisa de nada: não mexer é de graça. Avisar **no dia em que alguém abrir
aquele assento** precisa — e esse dia pode ser daqui a cinco anos, com outro
escrevente no balcão.

Então cada um dos três leva uma marca, e a marca aparece:

- **na ficha do assento**, no alto, com o motivo escrito por extenso;
- **ao lado do livro**, no quadro do assento (*"— por confirmar"*);
- **antes do botão de emitir certidão**, porque errar o livro só sai caro
  quando vira papel assinado.

E há um botão *"Confirmei no livro de papel"*: **aviso sem saída é aviso que
fica para sempre.** Se quem foi até a estante não tem onde dizer o que viu, o
próximo abre a ficha e vê o mesmo aviso — e na terceira vez ninguém lê mais.

### O defeito que essa marca teve, e o teste que o achou

A primeira versão marcava todo assento com `livro_a_confirmar IS NULL` — e um
assento **conferido** também está NULL. Rodar a carga de novo **ressuscitava a
dúvida** de quem já tinha ido à estante.

`NULL` estava querendo dizer duas coisas: *"nunca teve dúvida"* e *"teve, e
alguém resolveu"*. São estados diferentes, e um campo só não dá conta dos dois.
`livro_conferido_em` guarda o terceiro, e a ficha passa a dizer *"conferido no
livro de papel em tal data, por fulano"* — o que poupa a próxima ida à estante.

> **A lição**: marca que volta é pior que marca que nunca existiu — ela ensina o
> balcão a ignorar o aviso.

Se forem religiosos, a resposta fecha também uma das perguntas que já estavam
abertas: o B-Auxiliar era uma das **três séries do RCPN que estavam caladas**,
sem contador e sem aviso.

---

## O que o módulo faz, e por quê

| Decisão | O motivo |
|---|---|
| **Teor congelado + sha256** | averbação de amanhã não muda a certidão de hoje |
| **Numeração por exercício**, com `UNIQUE(numero, ano)` | onde a regra pode morar no banco, ela mora no banco |
| **Guarda quantos atos o assento tinha** | quem conferir depois sabe se ele andou |
| **As averbações entram inteiras no teor** | certidão que esconde averbação é certidão que engana |
| **Cancelar exige motivo, e o teor fica** | ela está na mão de alguém; não se apaga o que saiu |
| **Tabela própria, `rc_certidoes`** | certidão não ocupa folha nem entra na divisão tripartite |
| **A busca usa `nome_da_casa()` dentro do SQLite** | `LOWER('JOSÉ')` no SQLite é `josÉ`, e no civil quase todo nome tem acento |

---

## E os pais entraram na conferência de fraude

A ficha do assento conferia só o nome do **registrado**. Havia ali um comentário
meu dizendo que os demais nomes moravam em `dados_json` e entrariam "quando a
tela passasse a pedi-los".

**Eles nunca estiveram lá** — estavam no acervo, e a carga não os abria.

Agora que estão, entram no alerta: **registro de nascimento falso se faz com a
filiação de outra pessoa**, e nome de mãe é exatamente o tipo de nome que
aparece numa comunicação de fraude do malote.

---

## O que ainda falta no RCPN

- **a receita de custas** — não há o que medir: o E-Ofício selou 1.238 atos do
  civil por `/selo/civil/atos-em-geral` e mandou o `codigoAto` **vazio** em
  todos. A tela diz isso, em vez de mostrar um quadro de cobrança vazio
- **as remessas externas**: SIRC, CRC, IBGE e DNV
- **o dígito da matrícula**, acima — é pergunta, e não trabalho

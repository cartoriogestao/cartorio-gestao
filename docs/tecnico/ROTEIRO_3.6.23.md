# Roteiro da 3.6.23

*Serventia Extrajudicial de Cidade Exemplo/MA, CNS 000000 — 28/08/2026*

**2.379 testes, todos passando.** O pacote é
`CartorioGestao_3.6.23.cgu`, SHA-256
`37cf1d137e48a3525f0457902a3e3c6b635ece33f802364d36886bed9a770930`.

---

## O que esta versão conserta, em ordem de importância

### 1. A folha de segurança se gastava em todo ato do Registro Civil

**Este é o mais caro, e ele vale muito além do casamento.**

O selo de cada ato leva — ou não — o número da folha de segurança em que a
certidão é impressa. Medindo o contrato do selador: **19 dos 100 caminhos do
civil pedem folha**; os outros 81 não, porque não imprimem certidão nenhuma.

O sistema reservava e dava baixa numa folha para **todos**. Dois prejuízos:

- averbação, anotação e retificação gastavam papel que ninguém imprime; e
- **com o estoque vazio, esses atos eram lavrados SEM SELO**, com a tela
  dizendo que faltava folha de segurança para um ato que não usa folha nenhuma.

Ou seja: acabar o papel travava o selo de **metade do Registro Civil**, por um
motivo que não existia.

### 2. O selo do casamento

Um selo só, comprado na habilitação e reaproveitado no assento — sua decisão.
Ao clicar **casamento celebrado** na ficha da habilitação, o número passa a
constar também no assento, que sai da lista de atos sem selo sem ninguém
comprar nada.

**Quando a habilitação é de outra serventia** (item 14.1.6), o assento compra
selo próprio, citando o selo e o cartório de lá. A tela de lavrar casamento
pergunta de onde veio a habilitação: **em branco significa "foi aqui"**.

> Esse campo é a chave de uma decisão de dinheiro, e por isso ele é uma
> pergunta e não uma dedução. O assento é lavrado **antes** de ser amarrado à
> habilitação — se o sistema deduzisse "não tem habilitação ligada, logo é de
> fora", compraria selo em todo casamento normal.

### 3. A conversão de união estável ia pelo endpoint errado

O contrato tem caminho e schema próprios para ela, e neles o **número do
processo da união estável** é obrigatório — não é o número da habilitação. A
ficha tem campo para ele, e o selo recusa sair sem ele **no balcão**, e não na
rede vinte segundos depois.

### 4. O registro de proclamas seria recusado pelo aparelho

Faltava um campo obrigatório no envelope. Corrigido.

---

## O que esta versão acrescenta

### A remessa do IBGE saiu do impasse

Desde a 3.6.22 o sistema sabia o **layout** do arquivo e mesmo assim não
conseguia gerá-lo: o arquivo pede **código** de município (`21`, `07001`) e o
sistema guarda **nome** («Cidade Exemplo»).

O acervo tinha a resposta em duas tabelas que ninguém abrira, e a **carga nova
as traz**:

- os **5.570 municípios do Brasil**, com o código do IBGE de cada um;
- o **cabeçalho desta serventia** — UF 21, município 07001, distrito 05,
  cartório 01 —, que é o que a casa mandava de verdade.

As duas se conferem sozinhas: o código de Cidade Exemplo é `2198765`, que é
exatamente `21` + `07001` do cabeçalho.

### O assento passou a guardar o que só o IBGE usa

Na tela de lavrar: **onde a criança nasceu**, **se o parto foi gemelar**, o
**número da DNV** e o **número da DO**. Com caixa de seleção nos dois que têm
catálogo — código de IBGE digitado à mão é erro que ninguém confere.

> O catálogo de «onde nasceu» **pula do 3 para o 5**. Quem digitasse 4
> acertaria o tipo do campo e erraria o conteúdo, e o IBGE recusaria o
> trimestre inteiro meses depois sem dizer qual linha.

**Isso não sai na certidão** — a tela diz isso. Serve à remessa trimestral, que
é obrigação da serventia (Lei 6.015/1973, art. 49). Pergunte enquanto o
declarante está no balcão com o papel na mão; depois vira telefonema para a
família.

### O e-Proclamas na ficha da habilitação

Campo para o protocolo que a Central devolve — é ele que prova a publicação, e
sem esse número, meses depois, ninguém consegue mostrar que ela aconteceu.

---

## Os passos

**1. Feche o sistema.** Ninguém usando.

**2. Faça o backup**, e confira que ele terminou.

**3. Aplique** `CartorioGestao_3.6.23.cgu` pelo `ATUALIZAR_SISTEMA.cmd`.

**4. Confira o carimbo.** `VERSAO.txt` e `install.json` têm de dizer **3.6.23**.
Se disserem outra coisa, pare e me avise: carimbo que mente é pior que carimbo
nenhum.

**5. Rode a carga do acervo** — *Livros e acervo → Trazer o acervo do E-Ofício*.
Marque **tudo**, inclusive a caixinha nova **«IBGE»**.

Ao terminar, a carga do IBGE tem de mostrar:

| | |
|---|---|
| inseridos | **5.570** |
| rejeitados | **68** — municípios sem código no acervo, e a rejeição fica escrita |
| cabeçalho | **4** configurações trazidas |

Se os números forem outros, me avise antes de seguir.

**6. Confira o quadro da numeração**, que aparece logo abaixo da carga. As
pendências que sobrarem são as que só você pode informar.

---

## O que continua esperando você

**Os quatro cliques da configuração do selador.** São seus, e sempre foram: a
senha do aparelho não passa por mim nem entra no banco.

**A senha do selador está em texto puro no acervo do E-Ofício, e é fraca.**
Peça a troca a quem mantém o aparelho (FPFTech/TJMA).

**O certificado do selador venceu em 10/11/2025.** Não impede de selar — o
sistema fixa o certificado, e fixar é dizer «é esta máquina, eu conferi». Você
pediu para ser lembrado depois que tudo estivesse rodando; está lembrado.

---

## O que fica para a próxima passada

**As pessoas do assento.** O sistema lavra o assento com o **nome** de quem é o
registro, e mais nada sobre a pessoa: `rc_pessoas` guarda pai, mãe e avós — que
a carga trouxe —, e não o registrado, os nubentes nem o falecido.

O IBGE pede, dessas pessoas: sexo, data de nascimento, naturalidade, residência
e estado civil. Enquanto elas não existirem no assento, a remessa do ato **novo**
sai com «ignorado» nesses campos — que é o que o próprio IBGE manda fazer com o
que não se sabe, mas é remessa aceita e vazia.

**E não é só a remessa.** É a certidão de casamento e a de óbito também: as duas
descrevem pessoas que o sistema ainda não guarda por inteiro. É o coração do
Registro Civil, e é o próximo trabalho.

A lista do que falta **aparece na tela**, por espécie — não neste documento.
Documentação não avisa ninguém.

# O selo do casamento, medido no contrato

*28/08/2026 — Serventia Extrajudicial de Cidade Exemplo/MA, CNS 000000*

## A decisão do oficial, e o erro meu que ela corrigiu

> **«O selo é emitido uma vez apenas. Ele é reaproveitado apenas no assento, mas
> já foi emitido na habilitação.»**

É **um selo só**. Ele é comprado quando a habilitação é expedida, e **aparece**
de novo no assento de casamento — que não compra nada.

Eu havia entendido errado a resposta anterior dele — *«dois selos, ambos saindo
na habilitação e do assento»* — como **duas compras**, e cheguei a construir um
segundo envelope, para `/selo/civil/casamento`. Não eram duas: é um selo que
aparece em dois papéis.

**E a tabela de custas dizia isso o tempo todo, com o texto na minha frente.** O
item `14.1.1` é um só:

> Habilitação **e registro**, lavratura de assento de casamento, inclusive o
> religioso com efeitos civis, e conversão de união estável em casamento,
> **compreendendo todas as despesas**...

Um item, um selo. Eu li a descrição, transcrevi-a num comentário do código, e
mesmo assim construí o segundo — porque estava lendo o **contrato do selador**
(que tem dois endpoints, e por isso parecia pedir dois selos) em vez de ler a
**tabela de emolumentos**, que é quem diz quanto se cobra.

> **Contrato diz como se manda; tabela diz o que se cobra.** Confundir os dois é
> como confundir o envelope com o dinheiro que vai dentro. O contrato ter dois
> caminhos não quer dizer que se paga duas vezes — quer dizer que o Tribunal
> quer saber de dois momentos do mesmo ato.

### Como ficou no código

- O **assento de casamento não pede selo ao aparelho**. A tela diz isso: *"o
  selo é o da habilitação, que já foi emitido; ele é anotado aqui ao amarrar
  este assento à habilitação"*.
- Ao amarrar os dois (botão **casamento celebrado**, na ficha da habilitação),
  `habilitacao.espelhar_o_selo_no_assento` copia o número para o assento. Ele
  sai da lista de atos sem selo sem que ninguém precise comprar nada.
- A função que monta o pedido de compra (`envelope_do_casamento`) chegou a ser
  **apagada** — e voltou, quando o oficial decidiu o caso da habilitação de
  outra serventia (abaixo). Ela existe hoje para **um caso só**, e o código diz
  isso no lugar onde ela mora. Função de comprar selo que fica pronta «para o
  caso de» é, neste projeto, a arma que alguém religa sem saber por que ela
  existia — já aconteceu cinco vezes. Aqui religá-la cobraria do casal duas
  vezes, e por isso há teste que exige que a chamada continue **dentro da
  guarda** que só a habilitação de fora abre.
- **Não sobrescreve selo que já está lá**: se alguém digitou um à mão porque o
  aparelho estava fora do ar, é esse que vale. O que está no papel assinado
  manda sobre o que o sistema deduz.
- **Funciona nas duas ordens**: o selo pode chegar depois da celebração
  (aparelho fora do ar no dia em que a habilitação saiu). Por isso espelhar é
  uma função chamada em dois momentos, e não duas linhas dentro de um deles.

### O caso da habilitação de outra serventia — decidido em 28/08/2026

Item `14.1.6` da tabela: *"lavratura de assento de casamento à vista de certidão
de habilitação emitida por **outra** serventia"*. O casal se habilita em outro
cartório e vem casar aqui. Ali não há selo desta casa a reaproveitar, porque
quem habilitou e selou foi o outro cartório.

**Decisão do oficial: este assento compra selo próprio, citando o de lá.** E o
contrato tem os dois campos exatamente para isso:

```
seloReferencia               o selo do ato de habilitação — o de lá
localRealizacaoHabilitacao   onde a habilitação foi feita
```

**Os dois caminhos são exclusivos por construção, e é aí que o dinheiro está
protegido.** O que os separa não é dedução do sistema: é uma coisa que o
escrevente **responde** na tela de lavrar o casamento —
`rc_assentos.habilitacao_serventia`.

| a coluna | o que o sistema faz |
|---|---|
| **vazia** | é habilitação daqui: o assento **não compra nada**, e recebe o selo dela quando você amarra os dois |
| **preenchida** | veio de fora: o assento **compra selo próprio**, citando o selo e o cartório de lá |

Deduzir isso — por ausência de habilitação ligada, por exemplo — seria arriscar
cobrar do casal duas vezes no dia em que a ligação ainda não tivesse sido feita.
**Onde o erro custa dinheiro do cliente, quem responde é a pessoa.**

O selo de fora é opcional (o contrato o marca `optional`): nem toda certidão de
habilitação traz o selo legível, e recusar o casamento por causa disso seria
impedir o ato pelo acessório. Mas a **serventia** é obrigatória quando o selo
vem: número de selo sozinho não diz de onde veio.

---

## Não havia precedente nenhum a imitar

Antes de construir, medi. Dos **26.130 selos** que esta serventia comprou em
seis anos:

| Caminho do selador | Vezes que esta casa usou |
|---|---|
| `/selo/civil/casamento/segunda-via` | **15** |
| `/selo/civil/casamento` (o assento) | **0** |
| `/selo/civil/casamento/habilitacao` | **0** |
| `/selo/civil/casamento/conversao` | **0** |

Nenhum selo de casamento ou de habilitação. Os quinze são segundas vias de
certidão. Não é que a casa não casasse — é que o E-Ofício não selava esses atos.

Sem precedente, o que se imita é o **contrato**. E lê-lo achou três coisas que
ninguém tinha medido — as três independentes da decisão acima, e as três
valendo por si.

---

## 1. A conversão de união estável ia pelo endpoint errado

O sistema mandava os três tipos de habilitação — civil, religioso com efeito
civil e conversão — pelo mesmo caminho. O contrato tem dois:

| Tipo | Caminho | Schema |
|---|---|---|
| Civil | `/selo/civil/casamento/habilitacao` | `DadosSeloHabilitacaoCasamento` |
| Religioso com efeito civil | `/selo/civil/casamento/habilitacao` | `DadosSeloHabilitacaoCasamento` |
| **Conversão de união estável** | `/selo/civil/casamento/conversao` | `DadosSeloHabilitacaoCasamentoConversao` |

E a diferença entre os dois schemas não é decorativa. No comum,
`numeroProcesso` é **opcional**; no da conversão é **obrigatório**, e a
descrição dele diz, com todas as letras:

> número do processo da união estável

Não é o número desta habilitação. É o da **união que está sendo convertida** —
a escritura, o processo ou o registro que a declarou, papel que o casal traz.

O sistema não tinha onde guardar isso. Agora tem
(`hc_habilitacoes.uniao_estavel_processo`, com campo próprio na ficha), e **o
selo não sai sem ele**: a recusa acontece no balcão, com a frase que diz o que
buscar, e não na rede vinte segundos depois.

> **Mandar conversão pelo caminho comum é o mesmo erro de selar óbito pelo
> caminho do nascimento**: passa perto, e não é.

---

## 2. O registro de proclamas seria recusado pelo aparelho

O Livro D registra o edital de proclamas, e ele sela pelo caminho da
habilitação — que é o que ele é. Só que aquele caminho pede `tipoCasamento`
como campo **obrigatório**, e o envelope comum do Registro Civil não tem esse
campo.

O ato seria lavrado, o pedido sairia, e o aparelho recusaria. Agora o registro
de proclamas monta pelo envelope da habilitação, com o item `14.1.2` da tabela
(«afixação, publicação e arquivamento de edital de proclamas») — que é item
**distinto** do `14.1.1`, e por isso continua sendo selo próprio.

---

## 3. A folha de segurança se gastava em todo ato do civil, e não devia

Esta foi a mais cara das três, e vale para muito além do casamento.

`papelMoeda` — o número da folha em que a certidão é impressa — aparece em
**19 dos 100** caminhos do civil do contrato:

**Gastam folha (19):** os quatro registros que já saem com a primeira certidão
(nascimento, casamento, natimorto, óbito) e as quinze segundas vias.

**Não gastam (81):** toda averbação, toda anotação, toda retificação, toda
certidão negativa, a habilitação, a conversão e a apostila — porque nenhum
deles imprime certidão em folha de segurança.

O sistema reservava e dava baixa numa folha para **todo** ato do Registro
Civil. O prejuízo era dos dois lados:

- uma averbação à margem gastava uma folha que ninguém imprimia; e
- **com o estoque vazio, ela era lavrada SEM SELO** — a tela dizendo que
  faltava folha de segurança para um ato que não usa folha nenhuma.

Ou seja: acabar o papel travava o selo de metade do Registro Civil, por um
motivo que não existia.

A regra passa a ser: **a folha se gasta quando o envelope a leva**. Não é lista
de espécies nem de tipos de ato — quem diz é o contrato, e há teste que lê o
`selador-doc` e confere que a lista do sistema é exatamente a dele, com o
número medido.

---

## Como os testes provam isto

`tests/test_selo_do_casamento.py` **abre o `selador-doc` e lê os campos de
verdade**, em vez de repetir aqui a lista deles. Um teste que transcrevesse os
campos provaria que eu copiei certo — e não que o envelope obedece ao contrato.
É a lição do comentário que afirmava medição sem ter medido.

E há um teste que garante que **não existe função capaz de comprar o segundo
selo**. A garantia contra cobrar duas vezes do casal não é um comentário
pedindo cuidado: é a ausência da ferramenta.

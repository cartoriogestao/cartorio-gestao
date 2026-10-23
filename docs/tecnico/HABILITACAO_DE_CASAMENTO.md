# A habilitação de casamento

Construída em 27/08/2026, a pedido do oficial: *"desenvolva melhor as novas
atribuições, especialmente o registro civil"*.

---

## O que faltava, e o tamanho disso

O sistema sabia lavrar o **assento** de casamento. Não sabia nada sobre as
semanas que vêm antes dele — os documentos, o edital, o prazo, a oposição, a
certidão. E é ali que o casamento se decide.

O E-Ofício também não sabia. Medido no acervo:

| | |
|---|---|
| tabela de habilitação | **não existe** |
| tabela de proclamas | **não existe** |
| o que ele guardava | três datas dentro do assento final: `dtmDataPublicacaoProclamas` (20 de 20), `dtmDataHabilitacao` (4 de 20), `bitHabilitado` (20 de 20) |
| o contador do Livro D | **1.358 proclamas registrados** |

Mil trezentas e cinquenta e oito habilitações aconteceram nesta casa, e nenhuma
delas deixou rastro além de três datas.

**Então não há precedente de FORMA a imitar, e o que se imita é a LEI.** Onde a
lei não decide, o campo fica e a decisão é do oficial.

---

## A ordem, e o que cada etapa protege

```
abrir  →  documentos  →  edital  →  [oposição]  →  habilitar  →  celebrar
```

| etapa | fundamento | quem protege |
|---|---|---|
| **documentos** | CC art. 1.525, I a V | a lei exige, e é o oficial que atesta terem sido cumpridos |
| **edital** | CC art. 1.527 | chama qualquer pessoa a opor impedimento |
| **prazo do edital (5 d corridos no código)** | Lei 6.015/1973 art. 67 §1º (legado CC 1.527: 15 d) | tempo para oposição — **revisão jurídica local** |
| **oposição** | CC art. 1.529 | terceiro que sabe de impedimento |
| **habilitar** | CC art. 1.531 | o oficial atesta que nada obsta |
| **celebrar em 90 dias** | CC art. 1.532 | vencido, o processo se refaz |

**Habilitar sem edital tira de terceiro o direito de opor impedimento** — e é o
impedimento que anula o casamento depois. **Habilitar dentro do prazo é o mesmo
que não ter publicado.** **Celebrar com a habilitação vencida é celebrar sem
habilitação.**

As três são recusas do domínio, e há teste que manda cada uma direto para a
função, sem passar pela tela.

---

## As decisões que valem explicação

**O checklist nasce com o processo**, e não se monta depois: item que alguém tem
de lembrar de acrescentar é item que fica de fora. São os cinco incisos do art.
1.525, e cada um vale **para cada nubente** — a certidão de nascimento de um não
supre a do outro.

**A prova de dissolução só entra para quem precisa dela** (inciso V, «quando for
o caso»). Pedi-la a quem é solteiro é pedir papel que não existe, e checklist com
item impossível é checklist que se ignora inteiro.

**Dispensar exige motivo escrito**, como no usucapião: dispensar é decisão do
oficial, e ignorar não é. O motivo fica no processo, e é o que a inspeção lê
quando perguntar por que a habilitação correu sem aquele papel.

**O módulo não julga o impedimento.** Se ele procede é matéria de direito, e a
decisão é do delegatário — o módulo registra o que ele decidiu, com o fundamento
escrito, e nunca decide por ele. É a mesma regra do usucapião e da lista de
fraudes, e há teste que varre os nomes públicos procurando `julgar`, `procede`,
`decidir_impedimento`.

**O teor do edital congela, com hash.** É papel que fica afixado e que alguém
pode vir contestar meses depois. E o `.odt` sai com **o teor que foi publicado**,
e não com o modelo remontado agora: remontar faria o papel afixado e o
reimpresso divergirem.

**O modelo do edital vem preenchido com os nomes.** Campo em branco num edital é
o que produz edital genérico — e o edital existe para dizer *quem* vai casar.
Mas é oferecido, não imposto: quem publica é quem assina.

**Os nubentes ficam em colunas, e não em tabela de partes.** São sempre dois,
nunca mais nem menos, e cada um tem os mesmos campos. Uma tabela de partes só
acrescentaria um JOIN para responder «quem vai casar», que é a pergunta que esta
tela mais responde.

**O «e agora?» vem calculado do estado**, na ficha e na lista. Num rito de
semanas essa é a pergunta que mais se repete, e ela merece resposta na tela e não
na cabeça de quem lembra. É a mesma peça do usucapião.

---

## O que ficou por fazer, e por quê

**O selo e as custas da habilitação.** O caminho do selador para habilitação
existe no contrato, mas esta casa nunca selou por ele — os 1.358 proclamas são
anteriores ao selo eletrônico ou saíram por outro caminho. **Não se sela por
caminho que a casa nunca usou**: até medir, a habilitação sai sem selo e a tela
diz por quê.

**O registro do proclama no Livro D.** O campo `proclamas_assento_id` existe e
está vazio: lavrar o assento do Livro D é ato do núcleo, com folha e número, e
merece a mesma passada que os outros. O contador já está semeado em **1.359**.

**A conversão de união estável** entra como tipo, mas o rito dela tem
particularidades (CC art. 1.726) que não foram medidas.

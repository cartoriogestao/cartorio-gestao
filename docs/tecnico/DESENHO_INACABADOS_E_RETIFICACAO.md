# Desenho: o expediente que se abastece sozinho, e o módulo de retificação de área

*29/08/2026 — a pedido do oficial, para ele ajustar antes de eu construir.*

> «Sobre os expedientes, eles seriam de **abastecimento automático**, pegariam
> todos atos que começaram e não terminaram no sistema, esses que citei seriam
> exemplos. Criar módulo para gerenciar a melhor aplicação disso, para moldar o
> que fica, o que sai, como melhora. Desenhe como acha que vai funcionar melhor
> e depois eu ajusto o que for preciso numa tela própria no sistema.»
>
> «vamos criar o módulo de processos de retificação de área e
> georreferenciamento.»

---

# PARTE 1 — O que começou e não terminou

## A decisão de fundo: é uma LENTE, e não uma segunda gaveta

A tentação é criar uma linha de expediente para cada ato inacabado. **Não.**

O ato já é o registro. Criar uma linha ao lado dele significa **dois lugares
guardando o mesmo fato** — e este projeto já sabe como isso termina: o
`normalizar_nome` copiado, o `VERSAO.txt` que dizia 3.2.1, a documentação em duas
pastas, os modelos em duas telas. **A cópia diverge no primeiro conserto**, e
aqui ela divergiria de um jeito caro: o ato seria concluído e o expediente
continuaria aberto — que é *exatamente* o relato #24.

Então a lista é **medida na hora**, das tabelas onde os atos já moram. Ato
concluído sai da lista sozinho, porque a lista é a pergunta e não a resposta
guardada.

O que **se guarda** é só o que não existe em lugar nenhum: a anotação do
oficial sobre aquele item — quem está cuidando, até quando, o que falta. Uma
tabela só, `ex_anotacoes`, apontando para (tabela, id).

## As fontes, e elas são declaradas

Cada fonte diz quatro coisas, e nenhuma delas eu invento:

| | |
|---|---|
| **onde** | a tabela |
| **começou** | a condição que faz o item existir |
| **terminou** | a condição que o tira da lista |
| **quando fica parado** | quantos dias sem andar |

As fontes que **medi hoje** no banco de produção:

| fonte | começou | terminou | quantos há hoje |
|---|---|---|---|
| escritura em rascunho | `nt_atos.situacao = EM_LAVRATURA` | lavrada | **1** |
| prenotação sem ato | `ri_protocolos` aberta | `ato_id` preenchido | *(a medir na versão nova)* |
| rascunho de ato do RI | `ri_rascunhos` | o ato lavrado | 0 — a tabela é da 3.6.29 |
| protocolo do balcão parado | `cx_protocolos` ABERTO | ENTREGUE ou CANCELADO | **640** |
| usucapião | processo aberto | decidido e registrado | 0 |
| habilitação de casamento | aberta | casamento celebrado | 0 |
| título de protesto | apontado | protestado, pago, desistido ou cancelado | *(a medir)* |
| ato sem selo | lavrado | selo amarrado | *(já há tela)* |
| ato sem cobrança | lavrado | cobrado | *(já há tela)* |
| expediente | recebido | respondido ou arquivado | **13** |
| tarefa | aberta | concluída | *(a medir)* |
| **retificação de área** | processo aberto | averbada | *(o módulo novo)* |

> **Nenhuma dessas é nova.** Todas já existem como tabela e como tela; o que não
> existe é **o lugar onde elas aparecem juntas**. Hoje, para saber o que a casa
> deve, é preciso abrir onze telas.

## A tela que MOLDA — «o que fica, o que sai»

É a que você pediu, e ela guarda três coisas por fonte:

1. **liga/desliga** — a fonte entra ou não na lista;
2. **quantos dias** até um item ser chamado de parado;
3. **de quem é** — a atribuição, para o balcão do civil não ver a fila do
   protesto.

Nada disso mora no código: mora em `ex_fontes`, e por isso você ajusta num
sábado sem programador. **Mas a fonte em si é declarada no código** — porque
uma fonte nova exige alguém saber onde o ato mora e o que o termina, e isso não
se digita numa tela. A tela liga e desliga o que existe; ela não inventa fonte.

> É a mesma divisão de `aj_config`: **quem pode usar a ajuda** mora no banco e
> você muda; **como a ajuda funciona** mora no código.

## O que ela NÃO faz

- **Não conclui nada.** Ela mostra e leva à tela do ato. Concluir é lá, com as
  regras de lá — as mesmas três recusas que já existem.
- **Não cria expediente.** Ver acima.
- **Não avisa por conta própria** enquanto você não disser quantos dias — alarme
  que soa sempre é alarme que ninguém ouve, e isto vai olhar **640 protocolos**
  no primeiro dia.

---

# PARTE 2 — Retificação de área e georreferenciamento

## O que se mediu, e ele muda o desenho

Eu esperava achar um punhado de casos. **Georreferenciamento é rotina nesta
casa** — o que faz sentido numa serventia rural, e não é o que a intuição diz.

Nas **1.508** fichas de matrícula com teor:

| termo | quantas fichas |
|---|---|
| INCRA | **767** |
| MEMORIAL DESCRITIVO | **385** |
| CCIR | 284 |
| GEORREFERENC… | **182** |
| SIGEF | 157 |
| ART | 138 |
| RETIFICAÇÃO | 96 |
| CONFRONTANTE | 87 |
| ÁREA REMANESCENTE | 28 |

E nos **1.243** atos: INCRA 127, CCIR 79, memorial 54, SIGEF 46, retificação 42,
georreferenciamento 38.

## E há precedente de FORMA, que é o que importa

Esta casa já escreveu estes atos, e **ela mesma distingue os dois casos no
rótulo**:

| a forma que a casa usou | quantas |
|---|---|
| `AVERBAÇÃO DE RETIFICAÇÃO DE ÁREA GEORREFERENCIADA` | 5 |
| `AVERBAÇÃO DE RETIFICAÇÃO DE ÁREA NÃO GEORREFERENCIADA` | 2 |
| `AVERBAÇÃO DE GEORREFERENCIAMENTO` | 1 |
| `RETIFICAÇÃO DE ÁREA` (com qualificadores) | 9 + variantes |
| `RETIFICAÇÃO DE BENFEITORIAS` | 1 |

O caso inteiro, para imitar:

> `AV-16/1.083 (PROTOCOLO Nº 10.814): AVERBAÇÃO DE RETIFICAÇÃO DE ÁREA
> GEORREFERENCIADA, CIDADE EXEMPLO, 01 DE FEVEREIRO DE 2022`

**A distinção georreferenciada / não georreferenciada é da casa, e não minha.**
Ela decide o rito: a georreferenciada traz certificação do INCRA e planta com
ART; a outra não.

## A forma é a do usucapião, e pelo mesmo motivo

`REVISAO_MODULO_RI.md` já dizia: *«estes não se resolvem com um modelo de texto.
São fluxos com prazo, notificação e decisão»*. A retificação é um deles — Lei
6.015/1973, **art. 213** —, e ela tem a peça que define tudo: **a notificação dos
confrontantes, com prazo de 15 dias**, cujo silêncio vale anuência (§ 4º).

Errar essa notificação é o que anula a averbação depois. É a mesma razão pela
qual o edital do usucapião tem dois saltos de dia útil.

**As duas espécies do art. 213 não são a mesma coisa:**

| | quem começa | o que exige |
|---|---|---|
| **inciso I** — de ofício | o oficial | erro evidente, sem alterar direito de ninguém |
| **inciso II** — a requerimento | o interessado | planta, memorial com ART, **anuência dos confrontantes** |

Deixar o balcão escolher seria deixar corrigir por ofício o que precisa da
anuência do vizinho — e o vizinho descobre quando vende.

## Antes de escrever uma linha: o Código de Normas do TJMA

Eu **não vou montar o rito de memória**. O `Código de normas TJMA
atualizado.pdf` está na casa, e foi ele que fechou o usucapião — inclusive
desmentindo uma correção que eu quase gravei errada. Vou ler a seção da
retificação e trazer cada regra **com o artigo ao lado**, como `us_tjma.py` faz,
com tela para você conferir.

E o que a lei não decidir, **fica como campo e a decisão é sua** — foi assim na
habilitação de casamento, onde não havia precedente de forma.

## O que o módulo NÃO vai fazer

- **Não averba sozinho.** Quem lavra é a tela do RI, que tem a corrente de hash,
  o selo, os emolumentos e o delegatário. É a decisão do CNIB outra vez.
- **Não julga a impugnação do confrontante.** Se ela procede é matéria de
  direito, e a decisão é do delegatário. Quinta vez que esta regra aparece.
- **Não calcula prazo que a lei não dê.** Onde o Código de Normas não disser, o
  campo fica e você preenche.
- **Não inventa área.** Área que não vem da planta certificada não entra: `A
  CONFERIR` e o campo com o nome do que falta.

---

## A ordem que eu proponho

1. **Ler o Código de Normas** na parte da retificação, e trazer as regras com os
   artigos — como `us_tjma.py`. *(mede, não constrói)*
2. **O módulo de retificação/georreferenciamento**, com o rito medido.
3. **O expediente que se abastece sozinho**, já com a retificação entre as
   fontes — senão ele nasceria sem a fonte que motivou o pedido.
4. **A tela que molda**, ligando e desligando fonte por fonte.

Ajuste o que precisar: eu construo o que ficar decidido.

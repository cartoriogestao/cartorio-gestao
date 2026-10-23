# O termo que vai ao livro é o da casa — e continua editável por você

> «Termo de nascimento, casamento e óbito vamos construir os nossos com os
>  requisitos legais e regulamentares, não utilizaremos os modelos ruins do
>  e-ofício, nem em papel.» — decisão do oficial, 30/08/2026
>
> «opção B» — decisão do oficial, 31/08/2026

## O que estava de pé, e o próprio código declarava

O comentário da tela dos modelos dizia, com todas as letras:

> «Não é isto que vai ao livro — o termo oficial sai de `rc_termo.montar`, dos
> treze modelos do E-Ofício.»

A decisão do oficial era outra havia um dia. O termo da casa existia,
construído dos requisitos legais, **e não era ele que ia ao papel assinado.**

E trocar sem mais nada custaria o **relato #28** («preciso ter controle geral
sobre os modelos»): os três termos estão no catálogo que ele edita, e os da casa
usam `{chave}` do `str.format` em vez de `{{ chave }}` do Jinja — o conferidor
do catálogo reprovaria os três, e ele perderia a edição justamente dos papéis
mais importantes do Registro Civil.

## As duas saídas que ofereci, e a que ele escolheu

| | o que ganha | o que custa |
|---|---|---|
| **A — trocar já** | o termo lavrado passa a ser o da casa hoje mesmo | você perde a edição dos três termos pelo catálogo |
| **B — ensinar o catálogo o formato novo** | os dois: termo da casa **e** editável por você | mais trabalho, e mexe no módulo dos nove papéis |

Ele escolheu **B**, e a saída não custou nenhum dos dois lados: o catálogo
**já aceitava conferidor próprio por módulo** — o Registro de Imóveis usa isso
para conferir contra uma matrícula de verdade. Os três termos do RCPN registram
o seu, que entende o formato deles.

## Como ficou

- O **padrão** dos três termos aponta para `rc_modelos_do_livro.TERMO_*`, o
  texto construído dos requisitos legais.
- O catálogo passou a **declarar o formato** de cada modelo (`JINJA` ou
  `CHAVES`), em vez de deixar quem lê adivinhar pela cara do texto.
- `rc_termo.montar` busca o corpo em `modelos_da_casa.corpo_de`: **sem linha na
  tabela vem o padrão da casa; com linha vem o que você escreveu.**
- A tela do catálogo confere os três com a **mesma função** que a lavratura usa
  — `rc_modelos_do_livro.conferir_corpo`.

**Conferir com uma régua e imprimir com outra** é como a tela passa a aprovar o
que o papel não sabe montar. É a lição da `normalizar_nome` pela terceira vez:
onde a igualdade importa, ela se constrói — não se supõe.

## O que a tela passou a dizer

São dois formatos nesta casa, e escrever no errado é o engano mais fácil de
cometer ali. A tela agora diz qual é o daquele modelo, **antes** de você
escrever:

- `CHAVES` — «uma chave», `{nome}`, sem `{% if %}` e sem repetição. As frases
  que só aparecem em alguns casos já vêm prontas do sistema, e o modelo escolhe
  apenas onde pô-las. Quem escreve o termo não deveria precisar de um `{% if %}`
  para dizer que um nascimento não é de gêmeos.
- `JINJA` — «duas chaves», `{{ a.numero }}`, com condição e repetição.

## O defeito que essa guarda impede, e por que ele é calado

**O `str.format` não estoura com o texto antigo.** Dado `{{ a.nome }}`, ele
devolve `{ a.nome }` — com uma chave só —, e **isso iria escrito no livro**, num
papel assinado, sem erro em lugar nenhum.

Medido no servidor em 31/08/2026: `mo_modelos` tem **zero linhas**, de modo que
hoje ninguém é alcançado. Quem editar amanhã, sem esta guarda, seria. Por isso a
recusa é na tela de editar — onde há tempo de consertar — e não no balcão com o
cliente na frente.

## Os defeitos que construir isto achou

Nenhum apareceu em leitura; todos apareceram ao montar um termo de verdade.

1. **O termo iria ao livro sem quem assina e sem a cidade.** A tela monta a
   serventia com `{cidade, uf, estado, registrador, titulo}`; as pontes do termo
   leem `ri_cidade`, `ri_uf`, `escrevente` e `funcao`. Sem a tradução o papel
   sairia com «neste Município de ____________» e **ninguém assinando embaixo**.

   Nenhum teste de mesa pegaria: eles montam a serventia com os nomes que a
   função testada espera. Quem pegou foi o teste que a monta **como a tela a
   monta**.

2. **As marcas do óbito chegavam como lista onde a ponte espera dicionário.**
   `do_assento` devolve a lista das quatro marcas com rótulo e estado — que é o
   que a **tela** precisa; a ponte pergunta `marcas.get("obito_eleitor")`. O
   resultado seria `'list' object has no attribute 'get'`: **HTTP 500 no meio da
   lavratura de um óbito.** E eu tinha acabado de corrigir a assinatura dessa
   mesma chamada sem olhar o **tipo** do que ela devolve.

3. **`MODELOS` é uma tupla e eu a tratei como dicionário.** `campos_do` é a
   função da casa que responde a isso, e usá-la é melhor que reescrever a busca:
   reescrita, ela divergiria no primeiro conserto.

## Duas coisas que eu chamei de defeito e a medição desmentiu

Ao ler o primeiro termo montado, apontei duas. **Nenhuma era.**

- A data do fato sai por extenso **e** em algarismos — «dezoito (18) de agosto
  (8) de dois mil e vinte e seis (2026) - 18/08/2026». É a convenção declarada
  da casa, escrita na ajuda do próprio campo.
- O sexo saiu `____________` porque o ensaio não o preenchia. Campo exigido
  vazio virando claro visível é o comportamento certo: **papel assinado com
  buraco no meio é pior que papel sem a informação — ele afirma que há um dado e
  não diz qual.**

Medir antes de consertar evitou dois «consertos» que teriam estragado o termo.

## Uma diferença em relação ao E-Ofício, para você saber

**O termo da casa não repete livro e folha no corpo.** No livro de papel o termo
**está escrito naquela folha**, e a matrícula de 32 dígitos que ele traz já
codifica as duas coisas (tipo de livro, livro, folha e termo). Repetir no corpo
seria afirmar duas vezes o que o próprio lugar do papel diz — e criar uma
segunda fonte para divergir da primeira.

Se você preferir que apareçam escritos, é ajuste de uma linha no modelo, pela
sua própria tela.

## Os testes que guardam isto

| arquivo | o que guarda |
|---|---|
| `test_rc_termo.py` | o termo montado do assento, nas três espécies |
| `test_rc_termo_tela.py` | a tela, o que fica gravado e o `.odt` |
| `test_modelos_da_casa.py` | a tela **aceita** o formato da casa, **recusa** o antigo e o claro inventado, e o conferidor é a **mesma** regra de quem lavra |
| `test_pontes_do_termo.py` | as pontes do casamento e do óbito |

O mais importante deles é `test_o_ajuste_da_casa_vence_o_padrao_tambem_no_termo`:
é ele que fica vermelho no dia em que o padrão voltar a vencer o que você
escreveu.

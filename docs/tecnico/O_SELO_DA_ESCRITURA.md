# O selo da escritura, e a anotação antes da lavratura — 17/09/2026

> «acrescenta o campo de anotacoes antes da lavratura tambem para as escrituras
> e atas notariais. Ja coloca no rascunho 778 a nota que precisa verificar
> numero de livro, termo e folha antes de lavrar e pedir para o robozinho
> ajustar conforme informacoes dos livros. e constroi o modulo de selo
> automatizado na escritura (se ja nao houver), ali consta pra inserir o selo
> manualmente»
>
> — o oficial

## 1. Não havia selo automático na escritura, e isso está medido

`ato_selado.CAMINHO_DAS_NOTAS` cobre as três mesas do balcão — reconhecimento
de firma, autenticação e cartão de assinatura —, e **o ato de livro não estava
lá**. Na tela da escritura havia um campo para digitar o número do selo à mão, e
só.

| | |
|---|---|
| atos de livro nesta casa | **263** |
| com selo gravado | **1** — uma ata, digitada à mão |
| selos de ato de livro no razão | **283**, todos do tempo do E-Ofício |

## 2. O caminho saiu do acervo, e o que o amarra é o livro e a folha

Os envelopes dos atos de livro levam `selo{escrevente, livro, folha}` — e é por
livro e folha que eles casam com o ato em `nt_atos`:

| caminho | envelopes | casou com | e com mais nada |
|---|---|---|---|
| `/selo/notas/procuracao/poderes-especificos` | 217 | **204 PROCURACAO** | — |
| `/selo/notas/procuracao/simples` | 22 | **22 PROCURACAO** | — |
| `/selo/notas/procuracao/venda` | 1 | **1 PROCURACAO** | — |
| `/selo/notas/ato-declarado/com-valor` | 28 | **17 ESCRITURA** | — |
| `/selo/notas/ato-declarado/sem-valor` | 15 | **14 ESCRITURA** | — |

**Zero cruzamento.** Nenhum caminho de procuração casou com escritura, e nenhum
de ato declarado casou com procuração. Os que não casaram são atos que a carga
não trouxe com livro e folha.

**E `/selo/notas/atos-em-geral` NÃO É O ATO DE LIVRO, embora o nome diga que
sim** — 739 envelopes, e **nenhum** deles traz `selo{livro, folha}`: não têm
onde casar. O item de 712 é o **13.30**, que a tabela do TJMA chama de
«Arquivamento, por folha do documento». É o guarda-chuva do balcão.

## 3. Quem escolhe o quê

**O VALOR DECLARADO ESCOLHE O CAMINHO DA ESCRITURA** — a mesma regra do ato do
RI, e aqui ela está escrita no próprio nome dos dois caminhos. `nt_atos.
valor_transacao` (em centavos) decide sozinho; a tela pode informar outro.

**QUEM ATENDE ESCOLHE ENTRE AS TRÊS PROCURAÇÕES.** A natureza que este sistema
guarda **não separa**: `OUTRA`, `DETRAN — Modelo Amplos` e `PESSOA EXEMPLO
S/A — PRONAF` aparecem em mais de um caminho. Os 204 de poderes específicos
contra 22 simples são 90%, e **correlação forte parece regra até alguém contar
as exceções** — é a lição do item da autenticação, de 27/08. Sem a resposta, o
ato fica lavrado e sem selo, dizendo por quê.

**O ITEM DA TABELA É PERGUNTADO**, com os que a casa usou naquele caminho em
ordem de frequência e com o nome do serviço ao lado — item de um uso em
duzentos é exceção, e não regra. Sem item marcado não sai selo, e a tela diz
isso: a média do que a casa costuma cobrar não serve ao caso concreto.

**A ATA NOTARIAL NÃO SELA SOZINHA.** Uma em 263 atos, com o selo digitado à
mão: não há caminho medido. *Não se sela por caminho que a casa nunca usou* — e
a tela diz isso, em vez de oferecer um botão que sempre recusa.

## 4. As formas do envelope, medidas campo a campo

```
com valor    partes, selo{...}, valorDeclarado{valorAvaliado, valorDeclarado}, ato{}
sem valor    natureza{descricao:"Outros", tipo:41}, partes, quantidade:1, selo{...}, ato{}
procuração   partes, quantidade:1, selo{...}, ato{}
```

- os 28 `com-valor` **não mandam `quantidade`**;
- os 15 `sem-valor` mandam `natureza{Outros, 41}` — em 15 de 15;
- `selo` leva `termo` em **153 dos 283**; este sistema o tem, e manda;
- `parteAto` vem `{nome}` em 429 e `{nome, documento}` em 185 — mandar
  `documento: ""` onde a casa mandava só o nome seria inventar um campo vazio
  que ela nunca mandou;
- `isento{value, motivo}` aparece em 8, todos procuração do INSS (art. 68-A da
  Lei 8.212/1991) — e **sem motivo escrito o sistema recusa marcar**.

## 5. O selo sai DEPOIS do lançamento, e não derruba o ato

O pedido leva livro e folha, que só existem depois de o ato entrar no livro.
É a mesma ordem do RCPN e do RTD.

**E aqui o selo que não sai NÃO suspende o ato — a razão é o próprio livro.** A
regra do item 1 («selo que falha suspende o ato para corrigir») existe porque no
RI corrigir e lavrar de novo resolve. No livro de notas não resolve: a folha e o
termo foram escritos, e o próprio sistema já recusa desfazer isso («ato já
lançado no livro não volta para lavratura — o livro já foi escrito»). Suspender
aqui seria desfazer no banco o que está escrito no papel.

O que fica no lugar é o caminho que o RI construiu em 15/09 para o mesmo
problema: **o botão de selar continua na tela**. Corrige-se o aparelho e sela-se
de novo, sem tocar no livro.

## 6. O selo à mão passa a entrar no razão

Era um buraco declarado neste projeto em **01/09** e ainda aberto: a tela
gravava `nt_atos.selo` direto — o número não era lido, o CNS não era conferido,
o selo repetido só era recusado dentro da mesma tabela, e **nada entrava em
`sd_selos`**, de modo que a tela «Selos» não via e a trava do razão ficava
desligada.

`ato_selado.registrar_selo_obtido_a_mao` faz as quatro coisas, e era **a função
pronta que ninguém chamava** — pela enésima vez neste projeto.

## 7. A anotação antes da lavratura

`nt_atos.observacao` **já existia, e estava vazia em 263 de 263**: nenhuma tela
a escrevia. Ela vira o lugar de «o que falta conferir antes de lançar no
livro», com duas colunas novas — quem escreveu e quando. Nota sem dono é nota
que, daqui a um mês, ninguém sabe se ainda vale.

**ELA NÃO É A ANOTAÇÃO À MARGEM, e as duas não podem se confundir.** Aquela é
ato: entra no livro, tem selo e não se apaga. Esta é nota de trabalho, existe
antes de o ato existir, e por isso aparece **antes do teor** — um aviso que mora
depois do botão é um aviso que ninguém leu. *A mesma palavra em dois lugares não
quer dizer a mesma coisa*, e por isso a ação se chama `anotacao_de_lavratura`, e
não `anotar`.

Depois de lavrado o ato, ela continua visível, como registro do que foi
conferido — e não editável.

## 8. A nota do rascunho 778 está escrita

Ordem dele, e ela foi escrita no banco que está rodando:

> «Antes de lavrar: conferir o número do LIVRO, do TERMO e da FOLHA, e pedir ao
> agente do sistema que ajuste conforme as informações dos livros.»

O ato 778 é a **escritura pública de divórcio consensual direto** de PESSOA EXEMPLO, aberta em 17/09 às 10h22, em lavratura e sem livro,
folha nem termo. A nota entrou com auditoria (`NT_ANOTACAO_DA_LAVRATURA`) e com
cópia do banco tirada antes (`VACUUM INTO`).

**Ela foi escrita por script, e o script fica** —
`tools/anotar_rascunho_de_notas.py`, que **só mede por padrão** e tem três
recusas: ato que não existe, ato que não está em lavratura, e anotação já
escrita (que aparece, e exige `--substituir`). Ele existe porque a tela sobe com
a próxima versão, e a nota era para hoje.

**As duas colunas de quem e quando ainda não existem naquele banco** — elas
nascem com a atualização. O script diz isso em vez de estourar, e a nota fica
lá esperando.

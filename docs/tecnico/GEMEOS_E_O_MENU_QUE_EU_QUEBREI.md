# Gêmeos, e o menu que eu quebrei outra vez

*30/08/2026*

---

# PARTE 1 — Os gêmeos, art. 234

> «Art. 234. No caso de gêmeos, deverá constar **no assento de cada um** a
> **ordem de nascimento**.
>
> Parágrafo único. Os gêmeos que tiverem o **prenome igual** deverão ser
> inscritos com **duplo prenome ou nome completo diverso**, de modo que possam
> distinguir-se.»

## O campo que já existia não respondia à pergunta

`rc_assentos.ibge_gemeo` está no sistema desde a remessa do IBGE, com o catálogo
medido: **1** não é gêmeo, **2** gêmeo, **3** trigêmeo ou mais, **9** ignorado.

Ele diz **se** é gêmeo. O art. 234 exige **qual é a ordem**.

Usar um pelo outro faria o assento **cumprir a remessa e descumprir a lei** — e é
a mesma armadilha da palavra que quer dizer duas coisas em dois lugares, que este
projeto já pagou com o `natureza.tipo` da certidão do Protesto, com o
`proprietario` do RI e com o `MODELO_PADRAO` que não é um modelo. Quarta vez.

Duas colunas entraram por isso: **`gemeo_ordem`** e **`gemeo_irmao_id`**.

## São dois assentos, e o modelo da casa confirma

«no assento de cada um». E o modelo `m08_Termo_de_G_meos` do E-Ofício é **um
termo por criança**, com a frase que aponta para o irmão: *«É o primeiro gêmeo a
nascer, irmão de …, matrícula n.º …»*.

Um termo só para os dois faria dois registros caberem num número — e cada pessoa
tem o seu.

## A ligação é recíproca por construção

Amarrar A a B já faz B apontar para A: `irmaos()` olha os dois lados da
comparação. **Depender de duas amarrações produziria o par pela metade** — e o
par pela metade é o que faz a certidão de um irmão não citar o outro.

## O § único é uma recusa que protege os dois

Gêmeos com o mesmo prenome «deverão ser inscritos com duplo prenome **ou** nome
completo diverso, **de modo que possam distinguir-se**».

**Dois irmãos com nome idêntico, mesma filiação e mesma data de nascimento são
duas pessoas que nenhum documento separa** — e o estrago aparece a vida inteira:
matrícula de escola, conta de banco, benefício.

O sistema **avisa antes de lavrar**, com o artigo. **Recusar não**: registro de
nascimento é imperativo legal (art. 250), e quem decide é o oficial. *Sétima vez
que esta regra aparece neste projeto: usucapião, fraudes, habilitação,
impedimento, inacabados, erro da serventia, e agora.*

**E a comparação ignora acento**, porque «JOSÉ» e «JOSE» são a mesma pessoa para
qualquer documento — e `UPPER` do SQLite é ASCII, o que já deixou o CNIB sem
achar ninguém por nome.

## Duas coisas do modelo do E-Ofício que não se copiam

**O cabeçalho traz a oficial anterior**, com endereço, telefone e e-mail — o
«carimbo que mente», que já custou caro aqui. Há teste que varre o módulo
procurando o nome, o telefone e o e-mail vazados.

**E há um «PRIMEIRO GÊMEO» solto no meio da frase**, logo depois de «irmão de
@nomenascido, matrícula n°» — sinal de campo mal montado no E-Ofício, que sairia
impresso na certidão.

---

# PARTE 2 — O menu que eu quebrei outra vez

## O defeito

Em 27/08/2026 o oficial disse: *«não tem uma lógica para encontrar»*. O
Administrativo tinha vinte e sete itens em coluna única. A regra que saiu dali:
**primeiro o que o balcão faz o dia inteiro, depois consulta e acervo, e por
último o que só o oficial mexe**; módulo com mais de seis itens ganha seções.

**Em 29 e 30/08 eu acrescentei sete itens ao menu do Registro Civil** — SIRC,
painel das comunicações, FUNAI, inacabados, retificação, CPF dos assentos
antigos, registro tardio, gêmeos —, **um a um, cada um logo abaixo do anterior**.
Ele passou de nove para **dezesseis, em coluna única, sem uma seção**.

> **Item novo entra onde é cômodo escrever, e não onde é cômodo achar.** É o
> mesmo defeito, pelo mesmo caminho, três dias depois.

## O teste que devia ter pegado tinha uma lista escrita à mão

`tests/test_menu.py` tinha:

```python
MODULOS_COM_SECAO = ("Tabelionato de Notas", "Registro de Imóveis",
                     "Protesto", "Administrativo")
```

O Registro Civil não estava lá porque, **quando essa lista foi escrita, ele tinha
nove itens**. Ele cresceu, e o teste continuou olhando para os quatro nomes que
alguém digitou uma vez.

**É a lição do menu um nível acima:** *lista escrita à mão noutro arquivo
envelhece na tarde em que se escreve* — e aqui o arquivo era o **do teste que
deveria guardar a regra**.

Agora ela se **mede**: `_modulos_grandes()` conta os itens de cada grupo e aplica
a régua. Um módulo que cresça amanhã fica vermelho no mesmo dia.

## E a régua tem uma faixa em que não decide — e isso ficou declarado

| | |
|---|---|
| **acima de 6 itens** | exige seção |
| **até 4 itens** | seção é ruído: separa um item do outro sem nada a separar |
| **5 e 6** | **quem decide é quem monta o menu** |

O Protesto tem **exatamente seis** itens e duas seções — «O balcão» e «O dia da
CRA» —, e elas separam coisas que são mesmo diferentes.

**Fingir que a conta decide essa faixa produziria uma das duas coisas ruins:**
tirar seção que ajuda, ou pôr seção que atrapalha. Declarar onde a régua não
opina é mais honesto que estendê-la até onde ela erra.

## Como o menu do Registro Civil ficou

**O balcão** — Assentos · Certidões · Habilitação de casamento · Termos a
escrever · Folhas de segurança

**Assento já lavrado** — Retificação e suprimento · Registro tardio · Gêmeos ·
CPF nos assentos antigos

**Comunicações e remessas** — *O que comunicar hoje* · Remessa do SIRC ·
Comunicação à FUNAI · Carga da CRC · Anotações devidas · Comunicações mensais ·
Remessa do IBGE

Os mesmos dezesseis itens, conferidos um a um: nenhum perdido, nenhum inventado.

**A ordem da terceira seção é a do aperto do prazo**, e não a da importância — o
IBGE fica por último por ter o prazo mais folgado, ainda que seja o único destino
com multa em dinheiro.

## Os números

| | |
|---|---|
| `rc_gemeos.py` | o art. 234, com a ordem e o aviso do nome repetido |
| `tests/test_rc_gemeos.py` | **40** testes |
| tela | `/rcpn/gemeos` |
| `tests/test_menu.py` | a lista escrita à mão virou medição |

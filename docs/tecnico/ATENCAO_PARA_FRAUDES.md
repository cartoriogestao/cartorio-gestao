# A lista de atenção para fraudes

Pedida pelo oficial em **26/08/2026**, com estas palavras:

> *"Recebemos pelo malote continuamente comunicações de fraudes. Quero incluir
> um módulo no sistema de controle, em que colocamos nomes e/ou documentos de
> pessoas envolvidas em fraudes, seja vítima ou fraudador ou nome que conste em
> documento fraudado, e o sistema alerta quando um ato for requerido ou
> cadastrado com um nome que consta na lista de atenção para fraudes."*

**Documentação não avisa ninguém, e pasta também não.** As comunicações chegam
continuamente e em papel; hoje viram uma pasta, e a pasta só serve para quem
lembra de abrir. O que protege a casa é o nome ser reconhecido **na hora em que
alguém o digita no balcão**.

---

## Onde ficou

| Tela | Para quem | O que faz |
|---|---|---|
| **Consultar fraudes** | **todos** | o balcão digita o nome que o cliente deu e vê na hora |
| **Atenção para fraudes** | oficial e gerente | a comunicação que chegou vira nome procurável |
| **O alerta** | onde o ato acontece | no alto da ficha do título, antes dos atos |

**A consulta é de todos, e isso é decisão e não descuido.** Pôr o balcão atrás
de perfil seria deixar a informação longe de quem precisa dela no momento em
que ela serve.

**O alerta não mora numa aba.** Ele aparece onde o ato acontece — aviso que
chega depois de o escrevente já ter lançado o ato chegou tarde. Esta casa
aprendeu isso três vezes na revisão de agosto.

---

## As três regras, e o motivo de cada uma

### 1. Alerta não é trava

Homônimo é a **regra**, não a exceção: há muitos José da Silva. Travar o ato
pararia o balcão para gente inocente — e recusar um ato é decisão do oficial,
não de uma lista.

O módulo **não tem função que recuse ato nenhum**, e há teste que confere isso:
ele varre os nomes públicos do módulo procurando `bloquear`, `impedir`,
`travar`, `recusar`. Se alguém acrescentar uma, o teste fica vermelho.

### 2. A vítima é quem se protege, e não quem se barra

Ela está na lista porque **o nome dela foi usado por outro**. Barrá-la seria
fazer com o inocente exatamente o que o fraudador fez.

Por isso o texto do alerta **muda com o papel**, e o da vítima diz o contrário
do do envolvido:

| Papel | O que o alerta diz |
|---|---|
| **Vítima de fraude** | *"O nome desta pessoa já foi usado por outro numa fraude comunicada. **Ela é quem se protege, e não quem se barra** — confira a identificação com atenção redobrada, e se for mesmo ela, o ato segue normalmente."* |
| **Envolvido em fraude** | *"Esta pessoa consta como envolvida numa fraude comunicada. Confira a identificação e leia a comunicação antes de lavrar."* |
| **Nome em documento fraudado** | *"Este nome consta em documento que foi comunicado como fraudado. Confira o documento apresentado contra o que a comunicação diz."* |

Os três papéis são os do oficial, e não uma classificação minha — ele escreveu
"seja vítima ou fraudador ou nome que conste em documento fraudado". Há teste
que guarda isso.

### 3. Alerta sem procedência não se avalia

*"Fulano está na lista"* não ajuda ninguém a decidir nada. *"Fulano consta na
comunicação tal, do órgão tal, de tal data, como vítima"* é o que permite
julgar — e quem julga é quem está no balcão, com o cliente na frente.

Por isso `origem` é obrigatório, e o cadastro recusa sem ele.

---

## Duas coisas que o pedido não pediu, e a mesma lógica cobra

### O documento vem antes do nome

Documento **não tem homônimo**; nome tem, o tempo todo. Os achados saem em
ordem de força, e a tela pinta os dois de cores diferentes.

Sem essa ordem, um alerta por homônimo afogaria o alerta por documento — que é
o que importa. O nome se avisa com a ressalva: *"nome bate por coincidência:
confira a identificação antes de concluir que é a mesma pessoa."*

### O que a casa já tem daquele nome

**A comunicação de fraude chega depois do fato.** Saber que a pessoa já tem
atos aqui é o que transforma um aviso numa diligência — e por isso a consulta
mostra, ao lado do alerta, o que esta casa já lavrou com aquele nome ou
documento.

---

## O que protege a casa não é o alerta: é o rastro de que ele foi visto

Se um ato fraudado passar apesar do aviso, a pergunta que vem é **"o sistema
avisou?"**. Sem registro, a resposta é uma opinião.

`fr_conferencias` guarda, a cada alerta reconhecido: quem viu, quando, onde,
sobre qual ato, e **o que decidiu** — só anotei que vi, conferi e o ato segue,
ou não lavrei o ato. Mais o que a pessoa escreveu ao conferir.

**Grava-se quando o operador reconhece, e nunca ao mostrar.** Tela de leitura
que grava é tela que fica presa no `busy_timeout` enquanto outro balcão lavra —
e há teste que abre a ficha duas vezes e confere que nada foi gravado.

---

## Tirar da lista exige motivo escrito

Comunicação de fraude é documento: o nome **não se apaga**, inativa-se. E o
motivo fica escrito mesmo se o nome for devolvido à lista depois — engano se
conserta à vista, e não apagando o que se disse antes.

---

## O defeito que este módulo teve, e como apareceu

Escrevi neste módulo uma função de normalizar nome — a que tira acento e caixa
para a busca — com um comentário dizendo que era **"a mesma"** de
`pt_schema.normalizar_nome`.

Não era. A minha devolvia **maiúsculas**; a da casa devolve **minúsculas**.

O efeito: a consulta achava pelo documento e **não achava pelo nome**. O alerta
mais importante do módulo — o nome que alguém digita no balcão — simplesmente
não disparava.

**Nenhuma releitura pegou.** Quem pegou foi o teste de tela, que conferia se a
consulta mostrava os atos que a casa já tinha daquela pessoa.

A função agora se **importa**, e não se copia. E a direção do import — um
módulo das seis atribuições puxando de um módulo do Protesto — é feia, e é
menos ruim que a alternativa: uma terceira forma de normalizar nome faria a
busca da fraude achar coisa diferente da busca do protesto para o mesmo nome.

> **A lição**: um comentário que afirma "isto é igual àquilo" é uma afirmação
> que ninguém verifica. Se for importante que sejam iguais, importe — ou
> escreva um teste que compare as duas.

---

## As seis portas, ligadas

O alerta aparece em toda porta por onde uma pessoa entra nesta casa:

| Onde | Quem se confere |
|---|---|
| Protesto — ficha do título | o **devedor** e o **credor** |
| Registro Civil — ficha do assento | o **registrado** |
| RCPJ/RTD — ficha do registro | o **requerente** |
| Livro 3 — ficha do registro | as **partes** (emitente, credor, avalista) |
| **Balcão — protocolo** | o **interessado** |
| Notas — ficha do ato | as **partes** (outorgante, outorgado, testemunha) |
| Registro de Imóveis — ficha | as **partes** da matrícula |

**O protocolo é o «ato requerido» do pedido.** O oficial escreveu "quando um
ato for **requerido** ou cadastrado" — e o requerido é o balcão: onde o cliente
chega, dá o nome e pede. Avisar só quando o ato fosse lavrado seria avisar
depois de a casa ter trabalhado.

**No Registro de Imóveis o alerta vem ao lado da consulta ao CNIB**, que já
rodava ali. São duas listas de fontes diferentes, e nenhuma substitui a outra:
o CNIB é indisponibilidade; esta é fraude comunicada pelo malote.

### Uma macro só, e não sete cópias

O bloco do alerta mora em `templates/_fraude.html`. Escrevê-lo em cada ficha
daria sete versões divergentes do aviso que mais importa — e a consistência
aqui não é estética: **é o operador achar a mesma coisa, com as mesmas
palavras, em qualquer atribuição.**

É a mesma lição de `_cobrar.html`, que já serve as quatro atribuições do lado
do dinheiro. Há teste que abre as quatro fichas e confere que as quatro dizem
a mesma frase.

---

## O segundo defeito, e ele era pior que o primeiro

`LOWER()` e `UPPER()` do SQLite são **ASCII**. Nas tabelas que já têm
`nome_norm` — `pt_devedores`, `nt_ato_partes` — a busca funcionava; nas que não
têm, eu comparava `LOWER(nome)` com a forma normalizada.

**`LOWER('JOSÉ DA SILVA')` no SQLite é `josÉ da silva`**, e não `jose da silva`.

Ou seja: no **Registro Civil**, onde quase todo nome tem acento, a busca por
nome não acharia ninguém. Era o pior defeito possível numa lista de atenção — e
silencioso, porque a busca por documento continuava funcionando.

A correção põe **a própria função da casa dentro do SQLite**:

```python
con.create_function("nome_da_casa", 1, lambda v: normalizar_nome(v) or "")
```

e a consulta passa a comparar `nome_da_casa(nome) = ?`. É a mesma função que
grava as colunas `nome_norm`, e é isso que faz a busca achar a mesma coisa nas
tabelas que têm a coluna e nas que não têm.

**Isto não é acoplamento ao SQLite: é o contrário.** A regra continua em
Python, numa função só, e o banco apenas a chama.

> Os dois defeitos deste módulo foram **a mesma coisa duas vezes**: eu supus
> que duas formas de normalizar nome eram iguais. Na primeira, copiei a função
> e ela divergiu. Na segunda, deleguei ao SQL e ele não fazia o mesmo. **Onde a
> igualdade importa, ela tem de ser construída — não suposta.**

# Roteiro da 3.6.50 — o retorno do desenvolvimento nos 36 relatos

**Basta este pacote.** Ele exige a 3.3.0. Se você não aplicou a 3.6.49, este
traz tudo o que ela trazia — o termo da casa no livro e a tela dos modelos
dizendo qual marcador usar.

---

## O que muda

### O seu relato #35, atendido — e ele já estava construído

Você pediu um campo para o desenvolvimento escrever o que aconteceu com cada
problema, com a prova de quem foi resolvido ou a pendência de quem não foi.

**O campo já existia** — colunas, função, rota e tela — e estava **vazio nos 36
relatos**. Não faltava peça: faltava quem a usasse, e sou eu, porque a
informação que você pediu é o que foi feito no código.

Agora os **36 relatos têm nota**, com estado e prova. Abra *Ajuda → Problemas do
sistema* e cada um diz o que aconteceu.

### Como as notas chegam, e por que assim

Eu **só leio** o banco do servidor, nunca escrevo nele. Então elas viajam dentro
do pacote e o sistema as grava ao subir, como uma migração. Entregar um arquivo
para você aplicar poria em você um trabalho de digitação que é meu.

### Duas coisas que a passada nunca faz

- **Não sobrescreve o que você escrever.** Se você editar uma nota pela tela,
  aquela linha nunca mais é tocada — nem para corrigir. A sua nota vale mais que
  a minha, porque quem responde pela serventia é você.
- **Não fecha problema nenhum.** A situação continua sendo o seu clique. Dizer
  «atendido» é a minha opinião sobre o conserto; dizer que o assunto acabou é
  decisão sua — e já houve conserto que não era o conserto.

### O que as notas dizem, em resumo

| estado | quantos | quais |
|---|---|---|
| **Atendido** | 30 | com o teste, o arquivo ou a tela onde conferir |
| **Em andamento** | 5 | #20, #27, #33, #34, #36 e o que falta de cada um |
| **Depende de você** | 1 | #16, o endereço para onde o QR do selo deve apontar |

**Nenhum foi marcado atendido sem prova** — o sistema recusa, e está certo:
«foi feito» sem onde conferir é promessa.

### O que ainda não está feito, dito com todas as letras

- **#20** — subir e baixar o `.odt` do teor da escritura. A formatação foi
  feita; isto não.
- **#27** — a ficha de assinatura ainda não vai assinada pelo oficial, e faltam
  os dois campos de assinatura livre e o de rubrica.
- **#33** — a pesquisa dos selos por data, especialidade e usuário. Os três
  campos existem no razão dos 26.134 selos; falta a tela.
- **#34** — o encerramento por inatividade acima de 12h.
- **#36** — salvar o ato preenchido antes de lavrar existe **só** no Registro de
  Imóveis; você pediu em todos.
- **#16** — depende de uma decisão sua: **para qual endereço** o QR do selo deve
  levar. O código do selo já vai dentro dele; apontar para um endereço que eu
  suponha faria o cliente ler um erro com o selo desta casa na mão.

---

## Um defeito meu que o teste pegou, e vale você saber

Ao escrever as notas eu citei, como prova, nomes de teste **plausíveis** —
montados do assunto — em vez dos que existem: `test_ri_cnib.py`,
`test_us_tjma.py`, `test_expediente_tarefa.py`. **Quinze das trinta e seis
apontavam para arquivos que não existem.**

Isso é pior que não dizer nada: quem lê uma prova escrita **não vai conferir**,
porque o endereço estar ali já parece a conferência feita. Há teste que lê cada
prova como caminho de arquivo e fica vermelho se ela não existir — foi ele que
achou as quinze.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| rodapé de qualquer tela | **3.6.50** |
| *Ajuda → Problemas do sistema* | cada relato com um quadro «retorno do desenvolvimento», com estado, texto e — nos atendidos — a prova |
| o mesmo, no relato **#33** | «Em andamento», dizendo que os três campos existem e falta a tela |
| o mesmo, no relato **#16** | «Depende de uma decisão sua» |

Se os relatos aparecerem sem o quadro do retorno, a atualização não subiu.

---

## O que continua esperando você

Sem mudança: as 24 filiações de casamento a recarregar, o `unit_name`, o próximo
número do Livro de Casamento (1012 contra 39), os números do Registro de
Protestos e de Pagamentos, o Livro 6 de Apontamento, os três livros do RCPN sem
contador, as credenciais do SIRC e o INFODIP no TRE.

E mais uma, nova: **o endereço do QR do selo**, do relato #16.

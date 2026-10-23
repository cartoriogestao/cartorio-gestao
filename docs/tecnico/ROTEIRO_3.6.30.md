# Roteiro da 3.6.30 — dois relatos seus, e um deles era sobre mim

---

## 1. O número do problema — o relato #23

Você escreveu:

> «claude relacionou o problema 8, 9 e 20 como finalizados, mas não sei quais são esses —
> não há número nos problemas, não consigo saber qual o claude se refere como 8, 9 e 20»

**Você estava certo, e o defeito era meu.** O **relatório** que sai da casa numera cada
problema; a **tela** não numerava nada. Eu lia o relatório e falava por número; você lia a
tela e não tinha por onde achar. Duas vistas do mesmo fato, e só uma com endereço.

E eu continuei fazendo isso **depois** do relato — nesta semana falei em «#21 usucapião»,
«#19 CNIB» e «#10 layout», três vezes o mesmo defeito, com o seu relato aberto na lista.

**O que mudou:** a tela mostra `#8` na primeira coluna, e o relatório passou a escrever
`### #8 — …`. O **mesmo texto nos dois**, para quem lê um achar o outro sem traduzir. E
cada linha ganhou endereço próprio: `/ajuda/problemas#problema-8` leva direto a ela.

Agora, quando eu disser «o 8 está resolvido», você acha o 8.

---

## 2. Encerrar expediente — o relato #24

Você escreveu:

> «não tem botão para encerrar expediente. encerrei a tarefa e o expediente segue ativo.
> Melhorar a integração da tarefa e do expediente, permitir encerrar o segundo (…)»

**Medido antes de mexer:** 13 expedientes, **todos em RECEBIDO**, nenhum com data de
conclusão. Das 84 tarefas, **5 apontam para expediente** — uma para cada —, e o
**expediente 6 está com a tarefa dele concluída e ele ainda aberto**. É exatamente o caso
que você descreveu.

### O botão

Encerrar **já era possível**: bastava achar `ARQUIVADO` numa caixa com sete nomes de etapa
e clicar em «Atualizar etapa». Três passos e um nome técnico para a coisa mais óbvia da
tela — quem procura «encerrar» não acha «ARQUIVADO» numa lista.

Agora há um botão **Encerrar expediente**, com duas saídas que dizem o que significam:

- **Respondido** — saiu resposta, e a referência dela fica anotada;
- **Arquivado** — encerrado sem resposta a expedir.

São coisas diferentes, e a diferença aparece na correição.

### A integração com a tarefa

Ao concluir uma tarefa ligada a expediente, a tela **para de ficar calada**: diz de qual
expediente ela é, o que ainda está aberto nele, e manda ao lugar de encerrar.

**O expediente não fecha sozinho, e é de propósito.** Hoje é uma tarefa por expediente, e
seria fácil fechá-lo na primeira que fechasse. Mas o banco permite várias, e «uma
regularidade forte dentro de uma casa parece lei até alguém contar as exceções» — esta casa
já pagou por isso na letra da posição 566 do Protesto. Há teste que cria duas tarefas e
confere que o expediente **não** fecha na primeira.

E há uma lista nova, *Expedientes prontos para encerrar*: os que têm **todas** as tarefas
concluídas e continuam abertos. O expediente 6 está nela. Sem essa lista, ele só apareceria
a quem abrisse aquela ficha por acaso.

### A terceira parte não virou código

Você escreveu também:

> «Se aparece em tarefa, não precisa aparecer em expediente. Acho que os expedientes podem
> ficar restritos aos procedimentos abertos, como escrituras em rascunho, procedimentos de
> georreferenciamento, usucapião e etc.»

Isso **muda o que o módulo é**, e não é defeito: é desenho. Não escrevi por conta própria
— fica como pergunta. Se for o que você quer, o expediente deixaria de ser «tudo que entra
pelo malote» e passaria a ser «procedimento aberto que leva semanas», e o malote viraria
tarefa. É uma decisão com consequência: os 13 expedientes de hoje teriam de ser
reclassificados, e o histórico do malote mudaria de lugar.

---

## Como aplicar

1. Feche o sistema nas máquinas do balcão.
2. Rode **`ATUALIZAR_SISTEMA.cmd`**.
3. Confira **3.6.30** no rodapé.
4. Abra *Ajuda → Problemas*: cada linha agora começa com `#1`, `#2`, `#3`…
5. Abra *Expedientes prontos para encerrar*: deve aparecer o **2026/006**.

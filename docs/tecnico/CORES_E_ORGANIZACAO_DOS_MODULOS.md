# A cor de cada módulo, e a organização do menu

**Relato #32 do oficial, 30/08/2026:**

> «precisamos de um layout mais intuitivo, com cores diferentes, organização
> mais racional dos itens e subitens dos módulos (…) cada módulo deve ter uma
> cor no layout, cada submódulo deve ter uma derivação diferente dessa cor, e
> precisa reorganizar, unir o que é semelhante e colocar tudo em ordem»

---

## A cor é identidade, e não enfeite

Ela existe para que quem está no balcão saiba **em que atribuição está** antes
de ler o título — e para que **perceba quando entrou na errada**.

Por isso aparece em três lugares, e nenhum deles é o fundo da página:

| onde | o quê |
|---|---|
| a faixa do alto da tela | 4 px da cor do módulo |
| a etiqueta ao lado do título | o **nome** do módulo por extenso |
| a marca de cada grupo no menu | a cor **daquele** grupo, e não a da tela atual |

**Fundo colorido cansa a vista de quem passa o dia nele**, e há teste que
recusa pintar o corpo da página.

**E a cor vem sempre com o nome.** A cor sozinha diz «mudou de módulo»; ela não
diz para qual — e quem chega numa tela pelo link de outra precisa das duas
coisas. Cor sem nome é adivinhação.

---

## O matiz se escolhe; a cor se calcula

**A primeira paleta foi escolhida a olho, e a medição a desmentiu.**

| módulo | matiz que saiu | e o problema |
|---|---|---|
| Livros e acervo | 22° | **exatamente** o matiz de «atenção» |
| Registro de Imóveis | — | a 21 de distância de «feito» |
| Tabelionato de Notas | — | contraste de **3,6:1**, abaixo do mínimo da norma |

Dois módulos inteiros pintados com a cor que nesta casa quer dizer outra coisa —
e **cor de módulo que parece alarme faz o operador ler alarme onde não há**.

Então o que se escreve em `modulos.py` é o **matiz** — a decisão de quanto cada
módulo se afasta dos vizinhos e das cores reservadas —, e a cor sai de uma conta
que **garante o contraste por construção**: o brilho baixa até a cor sustentar
texto branco a 5:1. Amarelo e verde precisam de muito mais escurecimento que
azul e roxo, e é exatamente aí que uma paleta escrita à mão erra.

**Os matizes reservados**, que nenhum módulo colorido pode chegar perto:

| grau | quer dizer | onde |
|---|---|---|
| 4° | erro | `--danger` |
| 22° | atenção | `--warning` |
| 155° | feito | `--ok` |

Os seis módulos coloridos ficam a **40° ou mais** uns dos outros e a **30° ou
mais** das reservadas. Os dois últimos são neutros de propósito: **Livros e
acervo** é sépia (a cor de arquivo) e **Administrativo** é cinza — os dois com
saturação baixa, para não disputarem matiz com quem lavra ato.

> **Sépia é intrinsecamente da faixa do laranja**, a 6° de «atenção». Com
> saturação alta ele seria lido como alarme; com 0,25 vira marrom-acinzentado,
> continua sendo cor de arquivo e para de disputar. O primeiro valor era 0,55, e
> o teste o reprovou.

**A derivação do submódulo é calculada, e não escolhida.** Uma segunda paleta
escrita à mão seria uma lista a manter, e a seção que nascesse amanhã sairia sem
cor — ou com a de outro módulo.

---

## De onde a regra saiu, e por quê

Qual módulo é a tela em que estou **já se decidia** — mas dentro do
`base.html`, em dez linhas de `{% set %}`. Ali ela servia a uma coisa: abrir o
grupo certo do menu.

Agora serve a três — o grupo, a cor e o rótulo —, e regra que serve três lugares
não pode morar num template. Ela foi para `modulos.py`, e **é a mesma regra, não
uma parecida**: há teste que roda as duas contra **todas** as rotas do sistema e
exige que concordem em cada uma. Se divergissem numa só, o menu abriria um grupo
e a tela se pintaria de outro.

---

## Unir o que é semelhante

Medido no menu: **112 links, 111 destinos**. Havia **uma** duplicata —
`/modelos`, que aparecia como «Modelos de documento» no Registro de Imóveis e
«Modelos dos documentos» no Administrativo. Duas portas para a mesma sala, com
nomes quase iguais: é o relato **#12** («injustificadamente separados») noutro
lugar.

**Apagar um dos dois seria a saída preguiçosa** — quem está no RI e quer o
modelo da certidão do RI passaria a ter de sair do módulo. O catálogo **já sabia
de qual atribuição é cada modelo**, e nenhuma tela usava esse campo: agora a tela
filtra, e o link do RI leva aos 5 modelos do RI em vez dos 12 da casa.

**E a tela diz quando está filtrada.** Uma lista filtrada que parece a lista
inteira faz quem a lê concluir que a casa tem menos modelos do que tem.

Há varredor que recusa duas entradas de menu para o mesmo endereço. Ele compara
**endereços, e não rotas**: três itens do Registro Civil levam à mesma rota com
filtros diferentes, e estão certos — comparar por rota acusaria os inocentes.

---

## Colocar tudo em ordem

A regra da casa, de 27/08/2026: **primeiro o que o balcão faz o dia inteiro,
depois consulta e acervo, e por último o que só o oficial mexe.**

«O dia» do Registro de Imóveis tinha oito itens de **três naturezas**:

- o trabalho do dia — protocolo, matrículas, certidões, rascunho de ato
- **processos de meses** — usucapião e retificação de área, que têm prazo,
  notificação, edital e decisão fundamentada
- uma **consulta normativa** — «o que o Código de Normas exige», que não é
  trabalho nenhum: é referência para ler

Quem abria «O dia» procurando o que fazer agora lia oito linhas e achava quatro.
Agora os processos têm seção própria — *Processos que levam meses* — e a consulta
foi para *Consulta e acervo*.

---

## O que ficou para depois

**A cor ainda não entra nas tabelas nem nos formulários.** Ela marca a tela e o
menu; as listras das tabelas continuam neutras. Isso é deliberado por ora: cor em
excesso deixa de identificar e passa a decorar — e o efeito só se mede com o
sistema em uso, que é coisa que o balcão vai dizer.

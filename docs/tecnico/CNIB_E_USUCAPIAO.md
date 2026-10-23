# O CNIB que nunca avisou, e o usucapião medido no Código de Normas

**28/08/2026.** Duas respostas a duas decisões suas, e um defeito que apareceu no
meio do caminho — o pior tipo, porque falhava calado.

---

## 1. O CNIB — «avisar e preparar a averbação, ficando pendente okay do cartório»

Perguntei se o sistema devia averbar a indisponibilidade sozinho ao encontrar a pessoa, e
ofereci duas saídas: avisar só, ou averbar automático. Você respondeu com uma terceira,
melhor que as duas: **o trabalho fica pronto, e a decisão continua sendo de quem assina.**

### O que a medição dizia sobre averbar sozinho

Entre as **50.054 pessoas** das ordens do CNIB e as partes das **1.701 matrículas** desta
casa:

| Como se procura | Quantos batem |
|---|---:|
| por CPF/CNPJ | **0** |
| por nome | **6 pessoas, em 10 matrículas** |

E as seis são «Pessoa Exemplo», «Pessoa Exemplo», «Pessoa Exemplo», «Pessoa Exemplo» e dois «Pessoa Exemplo» — com ordens do **TJSC,
do TJPR, do TRF6** e de uma vara do **Rio Grande do Sul**.

Homônimo não é a exceção: é a regra. E averbar indisponibilidade na matrícula do homônimo
tira de um inocente o direito de dispor do imóvel dele — **e isso não se desfaz sozinho**:
para sair, precisa de ordem de cancelamento pela mesma via.

> **Eu tinha medido esse número errado antes.** Na primeira contagem, feita comparando o
> nome dos dois lados em maiúsculas, deram **quatro**. São seis: a comparação certa é a
> normalizada, sem acento e sem espaço sobrando, que é a que o sistema faz. **Contar de um
> jeito e o programa comparar de outro dá um número que parece medição e não é.**

### Os dois defeitos que desligavam o aviso — e nenhum aparecia

Ao construir a lista, a busca por nome devolvia **zero** em qualquer caso. Duas razões
independentes, e cada uma bastava sozinha:

**1. A exclusão olhava a tabela toda, e não o que se procurou.** Estava escrito:

```sql
p.documento NOT IN (SELECT documento FROM ri_cnib_pessoas WHERE documento IS NOT NULL)
```

— que é o conjunto de **todos** os documentos do CNIB. A condição só deixava passar quem
não tem documento nenhum, e **das 50.054 pessoas do CNIB, zero estão sem documento**. O
que ela queria dizer era «não repita quem eu já achei pelo documento» — e isso é a lista
que se **procurou**, não a tabela inteira.

**2. `UPPER` no SQLite é ASCII.** `UPPER('josé')` devolve `JOSé`, e o `.upper()` do Python
devolve `JOSÉ`: os dois lados da comparação nunca se encontravam em nome com acento — e
`ri_partes` tem **1.257** nomes acentuados. É a mesma pedra em que a lista de atenção para
fraudes já tropeçou, e a correção é a mesma da casa: comparar por coluna normalizada, com
a **mesma função** dos dois lados.

> **Com os dois de pé, o aviso de indisponibilidade da ficha só podia sair pelo documento.
> E por documento o número de achados é zero: o alerta nunca apareceu para ninguém.**

`ri_cnib_pessoas` ganhou `nome_norm`, preenchida pela `normalizar_busca` — a mesma que já
preenche `ri_partes.nome_norm`, do outro lado da comparação — com índice. A lista saiu de
**22,5 segundos e zero achados** para **0,1 segundo e dez**.

### A tela

*Registro de Imóveis → CNIB — o que espera seu okay.* Cada linha é uma ordem que atinge
parte de matrícula desta casa, com:

- **a averbação já redigida**, preenchida com o protocolo, a data, o juízo e o processo da
  ordem — o modelo `AV-INDISPONIBILIDADE` já existia no sistema; o que faltava era alguém
  preenchê-lo sozinho;
- **o achado por documento antes do achado por nome** — documento não tem homônimo;
- dois caminhos: *abrir a matrícula para averbar*, ou *não é a mesma pessoa*, **com motivo
  escrito**.

**O módulo não lavra o ato.** Quem lavra é a tela de ato do Registro de Imóveis, que já
tem a corrente de hash, o selo, os emolumentos e o delegatário — um atalho de um clique
pularia os quatro. Há teste que fica vermelho se alguém escrever aqui a função que averba.

**E a decisão fica gravada, que é o que faz a lista diminuir.** «Aviso sem saída é aviso
que fica para sempre»: na terceira vez que a mesma linha aparece, ninguém lê mais.

---

## 2. O usucapião — «eu monto do Código de Normas do TJMA e da lei, e você confere»

Você relatou que *«o cadastramento é muito simples e não parece ser maduro para processar
um usucapião no RI com confiança»* e pediu referências.

**O Código estava na casa, e eu quase respondi de memória.** `Código de normas TJMA
atualizado.pdf`, 249 páginas, na sua pasta de Downloads. A **Seção XIV — Da Usucapião
Extrajudicial** são os **arts. 747 a 761**, e os arts. 738 e 739 tratam dela dentro da
regularização fundiária rural.

> **E eu quase gravei uma correção errada.** `usucapiao.py` citava «arts. 747 a 761», e eu
> escrevi que a faixa estava errada porque a Seção terminaria no 760 — porque eu tinha
> lido até ali. Fui conferir antes de deixar a frase de pé: a Seção XV («Das Cédulas de
> Crédito») só começa no **762**. O 761 é de usucapião mesmo — é o imóvel edificado. **A
> citação que já estava no código estava certa, e a minha correção é que estava errada.**
>
> A lição não é sobre o artigo: é sobre a ordem. **Faixa de artigos se lê no cabeçalho da
> seção seguinte, e não no fim do trecho em que a gente parou de ler.**

### O que faltava, e é o que fazia o módulo parecer imaturo

O checklist tinha doze itens, **onze deles citando a Lei de Registros Públicos** e um só
citando o Código de Normas — com a faixa inteira, «arts. 747 a 761», sem dizer o quê.
Todo o conteúdo estadual estava de fora. Entraram:

**A justificação do óbice — art. 748.** É o item que mais faltava, e não é papelada: é a
pergunta que separa a usucapião de uma compra e venda que ninguém quis registrar para não
pagar ITBI. O requerente declara **por que a transação não pôde ser escriturada**, e o
registrador **alerta a ele e às testemunhas de que declaração falsa é crime**. O Código dá
sete hipóteses já justificadas (§ 1º) — imóvel invadido, alienante não localizado, pessoa
jurídica extinta irregularmente, transmitente sem CND, loteamento irregular, herdeiros que
recusam o inventário, inventários sucessivos — e a lista é **«entre outras»**, então ela
não fecha.

E o outro lado do mesmo artigo: **é vedado ao oficial formular exigência tributária** sobre
os negócios usados para provar a posse (§ 2º).

**O conteúdo da planta — art. 753.** O módulo pedia «planta» e «memorial» e parava aí. O
artigo lista: localização, medidas e área, perímetro, configuração geométrica,
**coordenadas UTM Datum SIRGAS 2000**, e a identificação de cada confrontante com
logradouro, número, quadra, bairro, matrícula, livro, folha e serventia. É aqui que um
pedido volta em exigência depois de semanas.

**O que a área tem a ver com a matrícula — art. 753, §§ 2º a 4º.** Quatro situações, e cada
uma leva o registro a um lugar diferente:

| Situação | O que acontece |
|---|---|
| Sem matrícula | abre matrícula nova, sem proprietário e sem registro anterior (art. 738) |
| Igual, e é o imóvel inteiro | registra-se **na própria matrícula** — não se abre nova (§ 2º) |
| Área usucapida **maior** | o requerente diz a razão da diferença; sem isso, ela é averbada na matrícula de origem (§ 3º) |
| Área usucapida **menor** | o requerente informa se há remanescente ou se é a área total (§ 4º) |

**O que NÃO impede** — e esta é a lista mais importante, porque é onde um balcão inseguro
trava um pedido bom: imóvel sem registro nenhum (art. 738), área menor que a fração mínima
de parcelamento (art. 758), ônus ou gravame na matrícula (art. 759, desde que os titulares
sejam notificados), e indisponibilidade averbada depois do início da posse (art. 760).

**A única vedação absoluta** é o imóvel objeto de garantia no Sistema Financeiro da
Habitação (art. 749). Não é caso de exigência nem de diligência.

**Os três deveres da indisponibilidade — art. 760**, e eles acontecem em momentos
diferentes do rito:

1. na fase das **notificações**, notificar por malote digital o juízo que a decretou, com o
   número do processo (§ 1º);
2. na **análise de mérito**, verificar se houve má-fé na cessão de direitos por quem tinha
   os bens indisponíveis — constatada, o oficial **pode** indeferir (§ 2º);
3. **depois do registro**, notificar o juízo de novo, com cópia da matrícula atualizada
   (§ 3º).

O do meio é o único que pode indeferir o pedido, e num parágrafo corrido ele se perde.

**O edital, e de quando se conta o prazo — art. 755.** São **dois saltos, e não um**: a
data da publicação é o primeiro dia útil *depois* da disponibilização na Central; os prazos
só começam a contar no primeiro dia útil *depois* dessa data de publicação. Quem ler o
§ 1º com pressa conta o prazo da disponibilização — e num edital, errar por um dia é
recomeçar o edital. Está em código, e o calendário de feriados vem de fora: feriado
municipal é coisa de cada casa, e um calendário escrito dentro do módulo envelheceria
calado.

**A impugnação — arts. 739 e 756.** O oficial não decide se ela procede: tenta conciliar
ou mediar, e num caso só remete ao juízo — impugnação de ente público sobre direito
indisponível. E o art. 739 traz a distinção que salva um pedido bom: dizer apenas que o
imóvel é terra devoluta do Estado *porque não tem matrícula* é impugnação
**injustificada**; apresentar matrícula com localização suficiente mostrando que o imóvel
está dentro de área arrecadada é **justificada**.

**A decisão — art. 757.** Ela **serve de título** para o registro: não se pede outro título
ao interessado. E «sem pendência de diligências complementares» é condição do artigo, não
conselho — o sistema já recusava decidir procedente com item pendente, e agora se sabe de
onde a regra vem.

**O imóvel edificado — art. 761.** Dois atos, nesta ordem: abre-se a matrícula do
**terreno**, e em seguida averba-se a benfeitoria ou a pendência de regularização dela. Com
o documento do art. 247-A da LRP, a matrícula sai já com terreno e construção, **sem
certidão previdenciária e sem declaração de dispensa**. E construção não regularizada não
impede escriturar nem registrar atos posteriores.

### Onde conferir

*Registro de Imóveis → Usucapião — o que o Código de Normas exige.* Cada regra com o artigo
do lado, para você abrir o PDF e ler. A tela não decide nada e não grava nada.

E há teste que percorre os arts. **747 a 761 mais o 738 e o 739** e fica vermelho se algum
sumir numa refatoração — artigo que some de um rito de meses só aparece na correição.

> **O módulo não julga.** Não decide se a impugnação procede, se a posse está provada, se o
> óbice está justificado. Ele diz o que o Código manda perguntar, com o artigo do lado, e
> quem responde é o delegatário. Quinta vez que esta regra aparece no projeto.

---

## 3. E o layout que você relatou

*«Layout das caixas de seleção muito separadas, falta listras nas tabelas.»*

As tabelas ganharam listra nas linhas pares. **Listra não é enfeite**: numa tabela larga,
como a dos lançamentos do caixa, é o que impede o olho de pular de linha no meio do
caminho.

> **E a correção quase criou um defeito.** `tr:hover td` é *menos* específico que
> `tbody tr:nth-child(even) td`: com a listra sozinha, a linha sob o mouse deixaria de
> acender justamente nas pares — metade delas. O realce está declarado nas duas formas, e
> há teste que guarda isso.

Os campos ficaram mais juntos: eram **18 px** entre campos no `grid2`, agora são 11. Num
formulário de dez campos, dezoito pixels empurram metade deles para fora da tela, e quem
preenche rola para achar o próximo.

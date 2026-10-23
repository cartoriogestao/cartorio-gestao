# Livro, folha e termo — como a numeração passou a funcionar

**17/08/2026. Versão 3.3.8.** Escrituras, procurações, substabelecimentos, revogações,
renúncias, testamentos e atas notariais.

---

## O que estava errado

A folha era digitada à mão. Disso vinham quatro coisas, todas de correição:

| O que acontecia | Onde estava |
|---|---|
| Nada impedia dois atos na mesma folha do mesmo livro | o índice `(livro_id, folha)` não era único |
| Nada impedia lavrar na folha 350 de um livro de 200 | a capacidade era gravada e nunca comparada |
| **Guardar o teor com o campo Folha em branco APAGAVA a folha do ato** | o mesmo `UPDATE` gravava teor e folha |
| O livro dizia sempre "folha 1 de 200", com 139 folhas escritas | `folha_atual` nascia em 1 e nunca era atualizado |

O quarto era o mais visível; o terceiro, o mais perigoso. Corrigir uma vírgula no teor apagava a
folha, em silêncio.

E o número de ordem era um `MAX()+1` filtrado pelo **ano de hoje**, não pelo ano da data do ato:
lavrar hoje um ato datado do ano passado devolvia um número já usado.

---

## A regra desta serventia

Definida por você em 17/08/2026, e é ela que o sistema aplica:

- **cada ato começa em folha nova.** Nenhum ato divide folha com outro;
- **conta-se frente e verso.** A folha 12 tem duas páginas: `12` e `12v`;
- **o ato ocupa folhas inteiras**, logo o número de páginas reservadas é sempre **par**. Sobrando
  o verso da última folha, ele não vai para o ato seguinte;
- **o termo é contínuo por série** e não reinicia quando o livro vira;
- **livro cheio encerra e o seguinte abre sozinho**, sem parar o atendimento.

### O verso que sobra — e que sai riscado sozinho

Um ato de 3 páginas ocupa 2 folhas e termina na frente da folha 2. O verso `2v` fica sem uso — e
**não fica em branco**: o art. 795, § 2º do Código de Normas manda que a escrituração seja
seguida, *sem claros ou espaços em branco*. Espaço em branco em livro de notas é o lugar por onde
se acrescenta o que ninguém declarou.

Depois do lançamento aparece o botão **"Imprimir a face 2v já inutilizada"**: sai um `.odt` com o
traço cobrindo a face, o dizer com o fundamento, e a linha de assinatura. Imprime-se sobre a folha
do livro. **Ninguém risca nada à mão.** O mesmo vale para as folhas que sobram quando um livro
encerra — a tela de livros tem "imprimir as folhas inutilizadas", e sai a série inteira de uma vez.

### Por que não se mexe na fonte para fechar em par

Foi a primeira ideia, e ela tem teto. Nenhum ato termina exatamente na última linha da página:
sempre sobra um pedaço depois do fecho, e esse pedaço pede traço de qualquer jeito. Mexer no corpo
da letra **não elimina o branco — muda o branco de lugar**. O que o controle de paridade evita é
outra coisa, menor e real: uma *face inteira* em branco.

E encolher quase nunca serve: passar de 3 para 2 páginas exige tirar um terço do espaço, e o corpo
12 vira 9,8pt. Livro de notas não se lê em 9,8pt daqui a quarenta anos.

O que existe hoje é a **sugestão**, na tela de lançamento, dentro da banda que você autorizou —
**só entrelinha, até 10%**. Ela aparece assim: *"o texto teria de crescer cerca de 33% para
alcançar o verso; a banda de entrelinha autorizada é de 10% — não cabe, inutilize a face"*. Em ato
longo (20 páginas ou mais) a conta fecha e a sugestão vem com o número.

**É sugestão, não ajuste automático**, e a razão está no código: para acertar contagem de página é
preciso *medir*, e o sistema hoje estima por tamanho de texto — quem decide a quebra é o
LibreOffice ao imprimir. Aplicar um ajuste calculado sobre estimativa trocaria um erro que se vê
(a face em branco) por um que não se vê (o ato que saiu com entrelinha diferente dos vizinhos e
mesmo assim não fechou em par).

O caminho para medir de verdade está quase todo montado: `ri_doc_extrair` já sabe achar o
`soffice`, `ri_web` já sabe dizer quando ele falta, e o `pypdfium2` já é dependência e conta
páginas. Gerar o `.odt`, converter, contar, subir um degrau da banda e repetir. Está descrito em
`notas_inutilizacao.sugerir_entrelinha`, para quem for ligar o fio.

---

## O caminho novo do balcão

**1. Abrir o ato** — escolhe o tipo, a data, o modelo. O ato nasce **em lavratura**: sem livro,
sem folha e sem termo. A tela mostra, à direita, para onde ele vai quando for lançado.

**2. Partes e teor** — como antes. Guardar o teor não toca mais em folha nenhuma.

**3. Lançar no livro** — o botão no fim da tela do ato. Você confirma **quantas páginas
escritas** o ato tem (o sistema pré-preenche uma estimativa a partir do tamanho do teor; quem
confirma é quem imprimiu), e nesse instante ele recebe, de uma vez:

- o livro,
- a folha inicial e a final,
- o número do termo,
- e passa a **lavrado**.

### Por que só no fim

Folha reservada para ato que não se lavrou vira **buraco no livro**, e buraco em livro de notas
não se explica em correição. Enquanto está em lavratura, o ato não ocupa folha, não tem termo, e
não vai a central nenhuma — a remessa à CENSEC filtra por atos lavrados.

**Depois de lançado, não se relança.** A folha foi gasta. Nem se o ato for cancelado depois: o
papel foi escrito, e a folha não volta para a fila. Ato errado se anota à margem, não se
renumera.

---

## Os livros

### Termo de abertura e de encerramento

Os dois deixam de ser opcionais. Deixando o campo em branco, **o sistema escreve o termo**, com o
número do livro, a quantidade de folhas por extenso e em algarismos (art. 795, § 4º), a
identificação da serventia e o CNS, e o nome de quem responde por ela.

O de encerramento diz o que costuma faltar: **até que folha foi usada, quais termos foram
lavrados, e quais folhas ficam inutilizadas**. Os dois saem em `.odt` pelos links da tela de
livros, para colar na primeira e na última folha do livro de papel.

### A virada do livro

Quando o ato não cabe no que resta, o sistema encerra o livro — declarando no termo as folhas que
sobraram em branco como inutilizadas — e o ato **inteiro** começa no livro seguinte. Ato não se
divide entre dois livros.

O livro seguinte é aberto automaticamente, marcado como `auto` na tela, com o termo de abertura
escrito. **O papel dele precisa estar pronto e rubricado antes disso**: o painel do tabelionato
avisa quando um livro chega às últimas dez folhas.

### Conferir o livro

Link `conferir` em cada linha da tela de livros. Responde as três perguntas que a correição faz:
há folha pulada, há folha repetida, a numeração dos termos corre sem furo.

---

## A numeração dos termos

Contínua por série, no mesmo desenho que o Registro de Imóveis já usa: contador explícito em
tabela (`nt_termos`), com quem fixou, quando e por quê — não um `MAX()+1`.

Na primeira vez, o contador é **semeado a partir do acervo**: as 45 escrituras e 213 procurações
do E-Ofício trouxeram número de ordem próprio, e começar do 1 daria termo repetido com ato de
1985.

A tela de livros mostra o próximo termo de cada série e permite corrigi-lo com motivo. O sistema
**recusa fixar número igual ou menor que o maior já usado** — isso criaria termo repetido.

Quatro séries compartilham livro por decisão de desenho, documentada em `notas_livro.py`:
procuração, procuração previdenciária, revogação e renúncia de mandato vão todas ao **Livro de
Procurações**, que é como a Seção X do Código de Normas as trata (arts. 831 a 833). Se a
serventia preferir separar, muda-se num lugar só, no `LIVRO_DO_ATO`.

---

## O acervo não é tocado

As 45 escrituras e 213 procurações trazidas do E-Ofício **mantêm o livro, a folha e o número de
ordem que já tinham**. Não recebem termo, não são renumeradas, e o sistema **recusa lançá-las**
no livro — a tela nem oferece o botão.

Os atos novos entram **depois** da última folha ocupada do livro. Um livro do acervo que estava
na folha 139 recebe o próximo ato na 140, não na 1.

### O desempate de folha, que estava faltando

A CENSEC identifica o ato pela chave *(livro, complemento do livro, folha, complemento da
folha)*. O acervo tem pares de atos na **mesma folha do mesmo livro** — reais, herdados do
E-Ofício. Sem complemento, a central **recusa os dois por duplicidade**.

A coluna `folha_complemento` existia, o `notas_censec.py` já a lia, e nada jamais a escrevia. Agora
a carga do acervo desempata sozinha: o primeiro ato de cada folha fica sem complemento — é o que
a central já conhece — e os seguintes recebem A, B, C. É idempotente e respeita a série: livro 27
de escrituras e livro 27 de procurações são dois livros diferentes.

---

## O que mudou no banco

Tudo aditivo. Nenhuma coluna foi removida, nenhum dado foi reescrito.

**`nt_atos`** ganhou `termo`, `serie`, `folha_inicial_num`, `folha_final_num`, `paginas`,
`verso_final`, `lancado_em`, `lancado_por`.

`folha` e `folha_final` continuam sendo **texto** — é o que sai no papel e o que a CENSEC recebe.
As colunas numéricas ao lado são as que o sistema usa para contar, ordenar e garantir unicidade.
No acervo elas ficam nulas, de propósito.

**`nt_livros`** ganhou `folha_inicial`, `aberto_por`, `encerrado_por`, `automatico`,
`folhas_inutilizadas`.

**`nt_termos`** é nova: o contador de termo, uma linha por série.

**Dois índices únicos parciais**, `ux_nt_atos_folha` e `ux_nt_atos_termo`. São **parciais** de
propósito: a condição `IS NOT NULL` deixa o acervo inteiro de fora, senão o índice se recusaria a
criar por causa das folhas repetidas do livro 27, e a atualização morreria na largada.

**`situacao`** ganhou `EM_LAVRATURA`. O acervo entra lavrado, como sempre foi.

---

## Concorrência

`db.transaction()` abre `BEGIN IMMEDIATE`, e o SQLite está em WAL com `busy_timeout` de 10
segundos: dois balcões lançando ao mesmo tempo serializam, e o segundo lê a folha já
incrementada pelo primeiro. Testado com quatro conexões simultâneas e dezesseis lançamentos:
dezesseis folhas distintas, dezesseis termos distintos, sem furo.

A rede de baixo são os índices únicos. Se algum caminho futuro escrever folha sem passar pelo
contador, o banco recusa em vez de aceitar duas escrituras na mesma folha.

---

## Perfis

O **auditor** vê tudo e não pratica ato: lançar no livro gasta folha e termo, e eles não voltam.
As telas de leitura do tabelionato não escrevem mais nada — antes, abrir a tela de livros
reconciliava o `folha_atual` no banco, o que travava o balcão por dez segundos quando outra
máquina estava lavrando.

---

## Testes

**81 testes novos**, dos quais 30 nasceram de uma revisão adversarial que encontrou doze defeitos
na primeira versão desta mudança — entre eles um que reescrevia a folha de uma escritura de 2011
com um clique, e um que devolvia uma procuração revogada à situação de lavrada.

Suíte inteira: **384 passando**.


---

## Anotação à margem — revogação, renúncia e substabelecimento

**Acrescentado em 17/08/2026, na mesma rodada.**

A revogação era lavrada no livro de procurações como ato novo, e a procuração revogada continuava
no livro anterior **intacta**. Duas verdades no mesmo acervo: quem pedisse certidão da procuração
de 2024 recebia uma certidão que não dizia que ela fora revogada em 2026.

A tabela `nt_ato_anotacoes` existia no esquema desde o início, com as colunas certas, e **nenhuma
linha do sistema a usava**.

### Como funciona agora

Lançando a revogação no livro, o sistema **escreve sozinho** a anotação à margem da procuração
revogada e a põe em *revogado*. O traslado e a certidão dela passam a sair **com a anotação
transcrita** — que é o ponto inteiro: a Lei 8.935/1994, art. 6º, II, manda expedir cópias
*fidedignas*.

Não conseguindo identificar o ato anterior com segurança, o ato entra na lista **Anotações
pendentes**, no painel do tabelionato. É a pergunta que a correição faz, e a resposta tem de ser
zero.

### O que o sistema NÃO faz, de propósito

**Não adivinha o ato anterior.** Quatro travas, e cada uma tirou um falso positivo real numa
revisão adversarial:

1. só procura quando o ato anterior é **desta** serventia;
2. só aceita candidato do **tipo** que aquele ato pode desfazer — revogação de mandato não alcança
   escritura nem testamento;
3. só aceita candidato da mesma **série de livro** — livro 27 de escrituras e livro 27 de
   procurações são dois livros de papel diferentes, e o importador do E-Ofício joga os dois números
   na mesma coluna;
4. havendo **dois** candidatos, não escolhe.

Sem a trava 2, uma revogação com `anterior_livro=27, anterior_folha=139` encontrou como "único
candidato" uma **escritura de compra e venda de R$ 150.000** e a marcou como revogada, com
anotação na margem que sai em todo traslado dela.

**Não apaga anotação.** Não há botão. Anotação à margem é escrita a tinta: errada, corrige-se com
*outra* anotação, que diz o que a anterior tinha de errado. E **não deixa revincular** o ato
anterior depois de a anotação já ter saído — clicar na linha errada da lista e depois na certa
deixaria duas procurações revogadas, e a errada invisível.

### O que se faz à mão

Revogação lavrada em outra serventia, ordem judicial, retificação: **Anotar à margem**, na tela do
ato. Marcando "lavrado em outra serventia", o texto padrão nomeia o cartório e o CNS.

Ato anterior de outra serventia **não se anota por aqui** — a anotação é feita naquele cartório,
por ofício. A lista de pendentes diz isso, com essas palavras.

---

## Manutenção diária — o `before_request`

**Corrigido na mesma rodada.** O `app.py` chamava `ensure_recurring_tasks` e
`ensure_overdue_escalations` em **toda requisição**, inclusive nos GET. As duas abrem transação de
escrita: tomavam o lock do banco inteiro para abrir qualquer tela.

Medido, com outro balcão dentro de uma transação de escrita: **onze telas de leitura devolviam
HTTP 500 depois de dez segundos cada**. Depois da correção, 200 em centésimos de segundo.

Agora roda uma vez por dia, com três cuidados que a revisão adversarial obrigou a acrescentar:

- **recuperação de atraso.** `ensure_recurring_tasks` avança um vencimento por chamada. Rodar uma
  vez por dia e pronto fazia uma obrigação *diária* nunca recuperar dia perdido — todo fim de
  semana atrasava dois dias, e em oito semanas a deriva medida foi de quinze dias. Agora roda até
  não criar mais nada;
- **reserva atômica.** A marca em `settings` sozinha era ler-e-depois-escrever: dois balcões
  abrindo o sistema na mesma manhã rodavam os dois e criavam tarefa duplicada. Quem altera a linha
  ganha o dia;
- **falha visível e dia devolvido.** Falhando, o erro fica em `settings`, e a marca do dia volta
  atrás — senão o dia se perderia em silêncio, e é justamente o dia em que algo está errado.

E o **traslado** era a última tela de leitura que ainda morria sob lock — não pela manutenção, mas
pelo `audit()`, que abre transação como qualquer escrita. A auditoria passou a esperar 800 ms em
vez de 10 segundos e, não conseguindo gravar, registra a linha no log do servidor em nível ERROR.
A troca é consciente: entre entregar o traslado sem a linha de auditoria na tabela e não entregar
documento nenhum, a serventia precisa do documento.

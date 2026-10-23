# Roteiro da 3.6.29 — o backlog do balcão zerado, e dois deles não eram o que pareciam

Esta versão fecha os **cinco** itens que restavam no backlog desde agosto. Os dois
últimos mudaram de tamanho quando eu fui medir — e acabaram sendo o mesmo papel.

---

## 1. Encerrar protocolo

**Onde:** na ficha do protocolo, painel *Encerramento*; e a lista nova
*Caixa → Protocolos parados*.

Atendimento que não virou ato — foi só um orçamento, o cliente não voltou, resolveu-se
por outro caminho — agora se encerra, **com o motivo escrito**. Duas palavras, porque são
duas coisas: **Entregue** (o atendimento foi resolvido) e **Cancelado** (não virou
serviço). Juntar as duas faria a lista do mês não distinguir o trabalho feito do trabalho
que não houve.

**Medido antes:** são **640 protocolos abertos**, todos de 2026 e **todos vindos do
E-Ofício** — 250 do Registro de Imóveis, 226 do Registro Civil, 101 de firmas. E **nenhum
tem um único item**: são «orçamento registro TÍTULO DE DOMÍNIO», «CERTIDÃO», «2ª VIA
NASCIMENTO».

**Protocolo com item já quitado não se encerra por aqui**, e a tela nem oferece: esse
dinheiro entrou no caixa, e encerrar faria o serviço sumir da lista e o valor ficar. O
caminho é o estorno, que deixa rastro.

E dá para **reabrir**, porque encerrar errado acontece. Na volta a situação é recalculada
dos itens — ela não se escolhe —, e **o motivo do encerramento fica gravado**, com a marca
de que foi reaberto.

> **O defeito aqui era o contrário do de costume.** Neste sistema a forma que mais se
> repete é «função pronta que nenhuma tela chama». Desta vez a **situação terminal estava
> declarada em três lugares** — no comentário do esquema, no rótulo da tela, e até numa
> guarda que evita sobrescrevê-la — **e nenhuma rota conseguia produzi-la**. Havia uma
> trava esperando um estado que nada criava.

---

## 2. e 3. Rascunho de ato, e ver a matrícula com o ato novo

**Onde:** na ficha da matrícula, painel *Rascunho do ato*; a tela *Como ela vai ficar*; e
a lista *Registro de Imóveis → Rascunhos de ato*.

Os dois débitos eram a mesma necessidade: escrever a averbação, **ver como a matrícula vai
ler com ela dentro**, e só então lavrar.

O rascunho **não toma número e não entra na matrícula**. Guarde, veja como fica, e volte à
ficha para lavrar — ou jogue fora.

**Por que o rascunho não fica junto com os atos:** `ri_atos` não tem situação. Ali todo ato
é definitivo no instante em que entra, e entra já fazendo duas coisas irreversíveis: **toma
o número** e **entra na corrente de hash**, que é o que prova que nenhum ato foi mexido
depois. Um rascunho ali dentro seria um ato que existe e não devia.

**A tela de pré-visualização parece certidão, e não é.** Alguém pode imprimir e entregar, e
aí a casa teria posto no mundo um papel afirmando um ato que não existe. Por isso a marca
**RASCUNHO — ATO NÃO LAVRADO** aparece em três lugares, e nenhum deles é um botão: ela
continua na impressão.

---

## 4. O «AV-28 no teor de ficha» — e este não era o que parecia

**Você escreveu uma linha:** «AV-28 aparecendo no teor de ficha do acervo». Parecia coisa
de tela. Fui medir antes de mexer.

Nas fichas que vieram do E-Ofício, **os atos moram dentro do texto da matrícula** —
`AV-28/1.490:-`, `R-33/314:-` — e não como linhas na tabela de atos. São **1.052 das
1.508** fichas com teor, e em **756** o texto passa à frente da tabela.

E o sistema calculava o próximo número contando **só a tabela**.

### O que eu quase te disse errado

Cheguei a dizer que eram **752 fichas** em que o ato novo nasceria com número já usado.
Fui medir o tipo da ficha antes de deixar a frase de pé:

- **743 são fichas de ACERVO**, e ali o sistema **já exigia o número à mão** e recusava
  lavrar sem ele. O problema nessas era outro e menor: **a tela não dizia qual era o
  número certo**, e quem digitava tinha de ir ao papel.
- **13 são fichas ESTRUTURADAS**, e é só nelas que o sistema numera sozinho.

**Treze, e não setecentos.** Mas são treze registros que sairiam com número repetido **sem
ninguém digitar nada**:

| Matrícula | A ficha traz | O sistema numeraria | Agora sai |
|---|---:|---:|---:|
| 314 | R-35 | 15 | **36** |
| 3199 | R-13 | 3 | **14** |
| 302 | R-12 | 6 | **13** |
| 8 | R-4 | 1 | **5** |

### O que mudou

- **Na ficha estruturada**, o próximo número passa a ser o maior dos dois — o da tabela e
  o do texto. A matrícula 314 agora numera **36**, e não 15.
- **Na ficha de acervo**, o campo do número **vem preenchido** com o que a ficha manda, e
  um aviso diz de onde saiu, **com as frases citadas**, para você poder discordar.
- **A recusa passou a olhar o texto.** Se o número escolhido já estiver escrito na ficha,
  ela recusa citando o rótulo e a frase.
- **Há uma tela com as 756**, em *Registro de Imóveis → Numeração dentro do teor*, com as
  **estruturadas no topo** — são as únicas em que o erro sairia calado.

### O que **não** se fez, e é o mais importante

**Não se cria ato a partir do texto.** A tentação era ler o teor e inserir as linhas que
faltam. Seria fabricar atos com **data, natureza e conteúdo adivinhados por um programa** —
e ainda pô-los na corrente de hash, que existe justamente para provar que nenhum ato foi
inventado. Um programa errando ali produz registro falso.

E há uma precisão que faz isto valer: o teor antigo cita atos de **outras** matrículas o
tempo todo («Transcrita no Lº 2-C, fls. 16 sob nº **R-1/503**»). O sistema só conta o
rótulo que **nomeia esta ficha** depois da barra. `AV-3` solto não conta — perde alguns
casos de propósito, porque **é melhor deixar de achar do que achar errado**: este número
vira o número de um registro.

---

## 5. O layout da certidão de inteiro teor — e era o mesmo papel do AV-28

**Medido:** `ri_certidoes` tem **369** certidões, todas de inteiro teor, e **uma só** guarda
o corpo — as outras 368 vieram do E-Ofício sem ele. Essa uma é a **6/2026, da matrícula
582**, emitida por este sistema em 18/08. E ela saía assim:

> **AV-28/582 — 2026-08-18**

A data do ato **em forma de banco**, dentro do documento que a serventia assina. Agora sai
**18 de agosto de 2026**.

E a peça já estava pronta: `data_extenso` era calculada ao lado de `data_ato`, com a mesma
função dos termos de livro. **O modelo é que não a usava** — sétima vez neste projeto que
a peça está pronta e quem devia chamá-la não chama.

> **E repare na matrícula: 582.** É a mesma do seu outro relato, o do AV-28 no teor. Os
> dois eram o mesmo papel, vistos de dois lados.

**E a validade passou a citar o artigo.** A certidão afirmava «VALIDADE: 30 dias, na forma
do Código de Normas da CGJ/TJMA», **sem dizer qual artigo**. Conferi no PDF que está na sua
pasta: **art. 53** — «(...) observando-se o prazo de validade de 30 (trinta) dias». O prazo
estava certo; faltava o endereço. Numa certidão, quem confere é o banco, o comprador e o
juiz.

---

## Como aplicar

1. Feche o sistema nas máquinas do balcão.
2. Rode **`ATUALIZAR_SISTEMA.cmd`**.
3. Confira **3.6.29** no rodapé.
4. Abra *Registro de Imóveis → Numeração dentro do teor*: com o seu banco ele deve listar
   **756 fichas**, as **13 estruturadas** no topo.
5. Abra *Caixa → Protocolos parados*: devem aparecer **640**.

O banco migra sozinho ao subir.

---

## O que continua esperando você

- **rodar a carga do acervo**, marcando o IBGE;
- os **quatro cliques da configuração do selador**;
- trocar a senha do selador com a FPFTech/TJMA;
- perguntar à FPFTech se o serviço de selo devolve o token do QR.

**O backlog do balcão está zerado.** Os itens que restavam em agosto — encerrar
protocolo, pré-visualizar matrícula, rascunho de ato, o AV-28 e o layout da certidão —
estão todos fechados.

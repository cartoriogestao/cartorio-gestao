# Fase 1 — o núcleo, concluído (versão 3.4.2)

**21 de agosto de 2026.** O uso do sistema segue suspenso; nada disto foi aplicado
no servidor. É código construído e testado, esperando a sua decisão de atualizar.

## O que é o núcleo, e por que ele veio antes das atribuições

A inspeção de 12/08/2026 cobra **as mesmas coisas** de Protesto, RCPJ, RTD e RCPN:
termo de abertura e encerramento, inutilização de folha e verso em branco, assinatura
ao final do ato, rubrica das folhas, encerramento diário do livro de protocolo e
continuidade da numeração ao migrar do livro físico.

Escrever isso quatro vezes produziria quatro versões divergentes do código mais
difícil do sistema — e o preço da divergência acabou de ser medido: em 18/08 a
numeração de matrícula, contada **por volume** em vez de **por serventia**, abriu a
matrícula 4011 depois de a 4013 já existir.

Então o núcleo veio primeiro. São seis módulos, **447 testes de regra** só do núcleo, e nenhuma
tela nova ainda — de propósito: a tela é da atribuição, a regra é do núcleo.

| Módulo | O que faz | Testes |
|---|---|---|
| `atribuicoes.py` | as 6 atribuições, 72 atos, 11 tipos de selo, 12 tipos de papel, os fundos | 54 |
| `livro_nucleo.py` | a geometria dos 24 livros: folhas, verso, páginas pares, transbordo, diário | incluso |
| `nucleo_schema.py` | as 5 tabelas: livro, lugar, inutilização, numeração, encerramento diário | — |
| `escrituracao.py` | abrir livro, achar lugar, lançar, inutilizar, encerrar livro, encerrar o dia | 37 |
| `custas.py` | emolumento, os quatro fundos, gratuidade e vigência **por data do ato** | 29 |
| `selo.py` + `selador.py` | o código do selo, o texto impresso, os 181 endpoints da API do TJMA | 157 + 170 |

No sistema inteiro: **955 testes passando**, 4 ignorados — eram 719 antes desta etapa.

---

## A trava que importa mais que o código

```sql
UNIQUE(livro_id, folha, verso, ordem)
```

Nenhuma revisão de código pegou o defeito de 18/08. O banco pegaria, se a regra
estivesse escrita nele. Agora está: **dois atos na mesma face da mesma folha do mesmo
livro não entram** — nem com dois balcões lavrando ao mesmo tempo, nem com o
`busy_timeout` estourando no meio. O teste que prova isso abre duas conexões de
verdade, porque teste de corrida com uma conexão só não testa corrida nenhuma.

Pelo mesmo motivo, um índice único parcial garante que **um ato tem um lugar de início
e não dois**.

---

## Três coisas que a numeração passou a fazer

1. **É contínua por SÉRIE e por SERVENTIA.** Livro cheio encerra com termo, o
   seguinte abre com termo, a folha volta a 1 — e o número de ordem **não volta**.
2. **É semeada do que já existe.** Começar do 1 sobre acervo importado repetiria
   número de 1985. O contador nasce do maior número já gravado na série.
3. **Consultar não escreve.** A tela de conferência lê o próximo número sem abrir
   transação de escrita. Parece detalhe: um GET que abre transação de escrita fica
   dez segundos preso no `busy_timeout` enquanto outro balcão lavra, e depois devolve
   500 na cara do escrevente.

---

## Inutilizar não é cancelar, e o sistema agora recusa confundir

Folha em branco dentro de livro escriturado é a porta aberta do art. 795, § 2º. Mas
folha **escriturada** não se inutiliza — o ato nela é que se cancela. São coisas
diferentes, e confundi-las apaga ato bom. O módulo recusa, com essa frase, na tela.

A inutilização exige **motivo escrito com pelo menos dez letras**, porque ele sai
impresso no termo e é o que a inspeção lê.

E a **sobra** do ato — o verso que fica em branco quando o registro ocupa folhas
inteiras — é devolvida pelo sistema, mas **não inutilizada por conta própria**.
Inutilizar é ato do oficial, com motivo. O sistema aponta; quem assina decide.

---

## O livro diário: dia sem movimento também se encerra

Protocolo de Protesto, de RCPJ e de RTD encerram **todo dia**, e não quando enchem.
Cada dia tem o seu livro, o termo diz o que foi protocolado, e **dia parado gera termo
dizendo "não houve movimento"** — porque o silêncio precisa estar escrito, senão não
se distingue de dia não escriturado.

Há uma consulta pronta, `dias_sem_encerrar`, que é a tela que a inspeção pede: não
basta encerrar, tem de dar para provar que não ficou dia aberto atrás.

---

## O motor de custas: o que eu achei conferindo, e uma correção minha

### O ISS não entra na conta do cliente

O cadastro de fundos do E-Ofício tem **cinco** linhas: FERC 3%, FEMP 4%, FADP 4%,
**ISS 5%** e FERRFIS 1%. Eu havia escrito, no código, que "são eles que aparecem na
linha do selo", no plural dos cinco. **Não é verdade, e a diferença custa 5% de todo
ato.** Conferindo:

- nos 39 textos de selo reais, um por prefixo: FERC em 39, FADEP em 38, FEMP em 38,
  FERRFIS em 4 e **ISS em ZERO**;
- a tabela de preços do Tribunal tem **quatro** colunas de fundo — FERMOJUPI, MP, DP
  e ferrfis — e **nenhuma de ISS**;
- em **400 valores reais** da vigência de 2026, o total fecha ao centavo com
  emolumento + os quatro.

O ISS é o imposto municipal sobre o serviço, devido pelo delegatário ao Município.
Não é repasse cobrado no balcão. Ficou registrado no código como fundo conhecido e
com `no_total=False`, para nunca mais ser somado por quem ler a lista de cinco e
supor. A correção está escrita no lugar onde eu errei, e não apagada.

### Os percentuais batem — menos um, e ele está declarado

Em 400 valores e 60 faixas da vigência de 2026, os quatro percentuais fecham **ao
centavo**. A única exceção é o item **15.17** (registro de conjunto de documentos de
arquivo, por folha): emolumento R$ 0,71 e FERC R$ 0,05, onde 3% dariam R$ 0,02. Sobre
setenta e um centavos, é arredondamento da origem. Está em
`DIVERGENCIAS_CONHECIDAS` para que a tela de conferência não o aponte todo dia como
se fosse novidade.

E quando um fundo divergir de verdade, o sistema **relata** — não corrige. Corrigir
por conta própria seria inventar preço.

### A vigência agora sai da data do ato

Antes o sistema só sabia responder "quanto custa hoje". Quem relavra ato de março de
2023, ou reimprime recibo de 2024, precisa de "quanto custava naquele dia" — e cobrar
pela tabela de outro ano é devolução de emolumento.

O E-Ofício tem as **18 vigências com data de início e fim**, em `tbVigencia`. O nosso
banco guardava só a marca `vigente`, e a vigência corrente era "a de maior código" —
funcionava por sorte. Agora:

- `EXPORTAR_CAIXA.ps1` traz `tbVigencia` e `tbFundo`;
- a importação grava o período de cada vigência e marca como corrente **a que contém
  hoje**;
- quando a data do ato não casa com nenhum período, o cálculo usa a corrente **e diz
  que usou**, num aviso na tela. Cobrar por tabela errada em silêncio é o que não pode.

### As nove gratuidades estavam escritas na tabela do Tribunal

Não inventei lista. Nove itens da tabela declaram isenção **no próprio texto**, com a
lei citada, e estavam sendo lidos como valor qualquer:

| Item | O que é | Fundamento citado pela tabela |
|---|---|---|
| 14.a | Registro de nascimento e primeira certidão | Lei 9.490/2011 (MA); Lei 9.534/1997 |
| 14.b | Registro de nascimento em Central ou Posto público | Lei 9.490/2011 (MA) |
| 14.c | Assento de óbito e primeira certidão | Lei 9.490/2011 (MA); Lei 9.534/1997 |
| 14.d | Assento de natimorto e primeira certidão | Lei 9.490/2011 (MA) |
| 14.13 | Registro tardio — isento, **compensável** pelo 14.5.1 | Tabela XIV |
| 14.1.8 | Casamento comunitário do Poder Judiciário | Tabela XIV |
| **14.10.1** | **Ato retificado, refeito ou renovado por erro da serventia** | Tabela XIV |
| 16.38 | Reurb-S — regularização fundiária de interesse social | Lei 13.465/2017 |
| 17.8 | Protesto por mandado a beneficiário de assistência judiciária | Tabela XVII |

**O item 14.10.1 é exatamente o caso de 18/08.** "É vedada a cobrança de emolumentos
em decorrência da prática de ato retificado, refeito ou renovado em razão de erro
imputável ao serviço registral." Está na tabela do próprio Tribunal — o que confirma,
por escrito e por norma, a decisão de cancelar o selo do AV-03 sem cobrar de novo.

Além dessas, duas gratuidades que **não dependem do ato, e sim de quem pede** —
hipossuficiência declarada e beneficiário de assistência judiciária. O sistema exige
o motivo escrito e diz o que precisa ficar arquivado, e **recusa** lançar sem isso.

Ato gratuito devolve **total zero e o valor que teria**: o selo de ato isento é
emitido do mesmo jeito, e o valor compensável precisa aparecer no relatório da COGEX
em coluna própria. Somar tudo junto é o erro que faz a serventia pedir compensação de
ato pago.

---

## O que vem agora, na ordem que você confirmou

1. **Protesto** — apontamento, intimação, protesto, pagamento, cancelamento, e o
   livro de protocolo que encerra todo dia.
2. **RCPN** — Livros A, B, B-Auxiliar, C, C-Auxiliar, D e E.
3. **RCPJ e RTD** — que já compartilham tabela no E-Ofício e vão compartilhar aqui.
4. **Registro Auxiliar do RI** (Livro 3).
5. **O cliente HTTP do selador** — a única peça que depende do Tribunal, e ela é a
   última da cadeia de propósito.
6. **A revisão manual, ato por ato, de cada atribuição.**

## O que continua faltando, e é seu

Duas coisas, e as duas estão na tela **Selador — Propriedades** do E-Ofício:

- **usuário e senha** do selador (campos *Username* e *Password*);
- a **URL de homologação** (campo *URL de Homologação*).

Não extraí a senha de lugar nenhum, de propósito, e ela não está em nenhum arquivo
que eu escrevi. E deixei `BASE_HOMOLOGACAO = None` no código em vez de adivinhar:
chutar endereço de homologação e pedir para selar achando que era teste é o tipo de
erro que gera selo verdadeiro e cobrado.

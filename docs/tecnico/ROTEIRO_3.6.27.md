# Roteiro da 3.6.27 — a DOI da serventia inteira

**28/08/2026.** Esta versão responde ao que você relatou pela janela da ajuda em 27/08 e
decidiu em 28/08.

---

## O que mudou, em uma frase

**A DOI deixou de ser do Registro de Imóveis e passou a ser da serventia:** as escrituras
do Tabelionato entram no mesmo arquivo dos registros, como você pediu.

---

## O que você vai ver de diferente

### 1. Na ficha de cada escritura — um painel novo

*Notas → o ato → **O imóvel — para a DOI***.

Ele só aparece nas **escrituras**, e tem:

- uma marca **«este ato transmite imóvel»** (e o contrário: marcar que não transmite tira
  o ato da lista para sempre — procuração, ata e declaração não entram na DOI);
- a **operação** e o **tipo de imóvel**, escolhidos de lista;
- **matrícula, endereço e área**.

**A operação não se digita.** Código digitado à mão é o que a Receita recusa sem dizer qual
linha, e a multa é da serventia. Se alguém mandar um código que não está na tabela dela, a
tela recusa e diz para escolher da lista.

### 2. Na tela da DOI — as duas atribuições juntas

*Registro de Imóveis → DOI*. Ela agora se chama **DOI da serventia**, e cada linha diz de
onde o ato veio: **Tabelionato** ou **Reg. Imóveis**. Sem essa marca, conferir viraria
procurar o ato em duas telas.

### 3. A conferência antes de gerar

No alto da tela, **antes do botão de gerar**, continua a conta: quantas declarações estão
prontas, quantas pararam, e uma tabela do que falta — agrupada do motivo mais comum para o
menos. É a mesma forma da conferência do IBGE.

**Agora as escrituras entram nessa conta.** Antes elas apareceriam na lista de baixo e
sumiriam da conta de cima — e a conta de cima é a que se lê antes de mandar o arquivo.

Quando uma escritura para, a tela diz **por quê**, com nome e tudo:

> falta a operação imobiliária
> não dá para saber de que lado PESSOA EXEMPLO está: a qualificação é «DECLARANTE»

E diz onde consertar: o que falta num ato do RI se digita na tela da CTP; o que falta numa
escritura se digita na ficha dela.

---

## O que o sistema decidiu sozinho, e o que ele recusa decidir

Para montar a declaração é preciso saber **quem alienou e quem adquiriu**. Isso sai da
**qualificação** que o escrevente escreveu na parte — e ela é campo livre: medi **24 formas
diferentes** nas 88 partes das 47 escrituras desta casa.

**O sistema lê o que dá para ler, e para no que não dá:**

| O que está escrito | O que ele faz |
|---|---|
| vendedor, cedente, outorgante, doador | quem **alienou** |
| comprador, outorgado, donatário, cessionário | quem **adquiriu** |
| **procurador**, testemunha, representante, intérprete | **não entra** — não é parte do negócio |
| proprietário, permutante, herdeiro, declarante | **pergunta** |

**O procurador é descartado antes de tudo, e isso tem um motivo caro.** «PROCURADOR DO
VENDEDOR» contém a palavra «VENDEDOR»: um programa desatento manda à Receita o CPF de quem
só assinou por outro, como se ele tivesse vendido o imóvel — cruzado com a declaração de
imposto de renda dele.

**E o que ele não sabe, ele não chuta.** «Proprietário» não diz de que lado a pessoa está:
na escritura 222 desta casa ele aparece **ao lado** de um vendedor e de dois compradores.
Nesses casos a escritura para e pergunta, em vez de mandar meia transação. Uma declaração
sem quem alienou **a Receita aceita** — e declaração aceita errada é pior que declaração
recusada, porque a recusada volta.

---

## O que fica faltando, e é honesto dizer

**A participação de cada parte (o percentual).** A Receita valida que a soma fique entre
99% e 100%, e `nt_ato_partes` não tem essa coluna. Não dividi em partes iguais por conta
própria: dois vendedores podem ser meeiros ou não, e percentual errado é declaração aceita
com o número trocado.

---

## Como aplicar

1. Feche o sistema nas máquinas do balcão.
2. Rode **`ATUALIZAR_SISTEMA.cmd`**.
3. Abra o sistema e confira, no rodapé, que diz **3.6.27**.
4. Abra *Registro de Imóveis → DOI* e veja o cabeçalho **DOI da serventia**.

Nada precisa ser migrado à mão: as colunas já existiam no banco.

---

## O que continua esperando você

Sem relação com esta versão, mas ainda de pé:

- **rodar a carga do acervo**, marcando o IBGE — sem ela `ib_municipios` fica em zero e a
  remessa não sai;
- **os quatro cliques da configuração do selador**, que só você faz;
- trocar a senha do selador com a FPFTech/TJMA;
- perguntar à FPFTech se o serviço de selo devolve o token do QR.

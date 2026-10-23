# Roteiro da 3.6.46 — o termo, a folha e o checklist da inspeção

*30/08/2026*

---

## Primeiro: **um arquivo só, e ele é o único que você precisa aplicar**

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.46.cgu` |
| onde | `C:\Users\<usuario>\Downloads\CartorioGestao\` |
| tamanho | 2.077.619 bytes |
| SHA-256 | `62a59eae68f516107a7a1e4cbc815f8bea5c41223ebfe38d4cae04215f2600f3` |
| arquivos dentro | 455 |

Ele traz tudo o que a 3.6.45 trazia, e mais cinco coisas. Se você ainda não
aplicou a 3.6.45, **aplique só esta**: o pacote é completo, não incremental.

**O banco migra sozinho ao subir.** A tabela nova desta leva é uma só —
`rc_checklist`. Nenhuma coluna é removida, nenhum dado antigo é tocado.

---

## O que mudou

### 1. O termo importado deixou de prometer o que não ia cumprir

Você apontou: *«aparentemente você está gerando uma expectativa de termo, que não
corresponde à realidade»*. Estava certo, e o defeito era exatamente esse.

O sistema listava **244 assentos** numa tela chamada **«Termos a escrever»**. Só
que esses 244 vieram do E-Ofício, e **o termo deles já existe — em papel,
assinado, no livro**. Ninguém ia escrever termo nenhum. A conclusão do módulo
estava certa e a tela dizia o contrário.

> **Lista é promessa.** Uma tela que enfileira 244 linhas está dizendo que há 244
> serviços a fazer. Explicar em prosa, embaixo, que não há, não desfaz a promessa
> — quem abre a tela lê o número.

O que passou a valer:

- **«Termos a escrever» mostra zero.** Porque zero é a verdade: nenhum assento do
  acervo espera termo.
- Os 244 têm **lista própria** — *Informações importadas do E-Ofício* — que **não
  é lista de trabalho**. Ela existe para consulta e para a certidão.
- **Você pode anexar o PDF do termo** de qualquer um deles, quando for
  conveniente. O sistema guarda junto do assento.
- **Gerar o termo virou um clique**, para o caso em que você precise — e não mais
  algo que o sistema propõe sozinho. Ele não imagina como o termo antigo ficou.

As informações importadas servem à certidão, que é para o que foram importadas.

### 2. A folha do livro sai em três colunas, frente e verso

Você perguntou: *«a regra das três colunas não está no relatório de exigências da
COGEX?»* — **estava**, e eu tinha procurado no lugar errado. Está na **página 49**
do Relatório de Inspeção Ordinária de 12/08/2026, e é cobrada em **quatro
livros**:

| livro | página | inclusive no verso |
|---|---|---|
| A-24 | 49 | **sim** |
| B-04 | 49 | **sim** |
| C-05 | 49 | — |
| D-03 | 50 | — |

Prazo: **30 dias**. Prioridade: **alta**.

A folha impressa agora sai como o livro de papel: **carta deitada, 279 × 215 mm**
— medida no **termo nº 8.369** desta casa, e não escolhida por mim —, dividida em

| coluna | o que leva |
|---|---|
| **Número** | o número do termo |
| **Termo** | o teor |
| **Notas, averbações e retificações** | a margem tripartite que a inspeção cobra |

**A coluna de notas vai nos dois lados da folha**, porque é o que a exigência diz
com todas as letras: *«inclusive no verso das folhas»*. Folha cujo verso não tem
margem é folha em que a averbação não cabe — e a averbação vem depois.

### 3. O checklist obrigatório antes de concluir o ato

Esta é a exigência de **prazo zero** e prioridade **crítica** da página 50:
padronizar assinaturas, gratuidade e categoria do selo nos atos futuros,
**aplicando checklist obrigatório antes da conclusão de novos atos**. A da página
49 diz o mesmo para emolumentos e destinações dos nascimentos.

Cinco itens, e **eles mudam por espécie** — emolumentos e destinações são
cobrados dos nascimentos; assinaturas, gratuidade e selo, de todos.

Duas escolhas que eu fiz e que você pode reverter:

- **O checklist avisa, e não trava.** Um ato urgente às 17h50 não pode ficar
  parado porque uma caixa não foi marcada.
- **O que ficou por conferir fica escrito**, e não só o que foi conferido. Uma
  marca que registra apenas o bom deixa o silêncio significar duas coisas: «não
  faltou nada» e «ninguém olhou».

**O acervo não entra nesta lista** — a exigência é dos *atos futuros*.

### 4. Um modelo de termo para cada ato

Nascimento, casamento e óbito, cada um com seu texto, sua lista de campos, seu
livro e o artigo que o rege.

**O de nascimento é o desta casa**: transcrevi o texto do **termo nº 8.369**, de
21/07/1994. Duas frases dele confirmam trabalho que fizemos ontem — *«não é gêmeo
único com este nome e 1º na ordem de filiação»* e *«a genitora na ocasião do
parto contava 29 anos de idade»*.

**Os de casamento e óbito dizem, na própria tela, que não são precedente desta
casa** — foram montados dos requisitos da Lei 6.015, do Código Nacional de Normas
e do Código de Normas do TJMA. Apresentar como medido o que não foi medido seria
pior que não ter modelo.

Se você tiver um termo de casamento e um de óbito em papel, eu meço os dois e
troco — é o mesmo caminho do 8.369.

### 5. Os formulários de preenchimento

**Registro Civil → Modelos dos termos.** Você preenche os campos e vê como o
termo fica antes de imprimir.

Dois cuidados que valem dizer:

- **Os campos saem do próprio modelo**, e não de uma lista escrita ao lado. Duas
  listas divergem no primeiro conserto, e a tela passaria a perguntar uma coisa
  enquanto o texto espera outra.
- **Claro em branco não some: vira o traço** `____________`, que é o que o livro
  de papel tem — e a tela lista quais ficaram. Campo em branco num termo assinado
  é claro que ficou por preencher, e o livro não aceita rasura depois.

**A idade da genitora não é calculada.** Ela é perguntada. Calcular onde a data de
nascimento da mãe falta daria idade errada num papel assinado.

---

## O que precisa da sua decisão

### a) Os dois termos que faltam medir

Casamento e óbito estão montados dos requisitos, e dizem isso na tela. Se houver
um de cada em papel, eu meço.

### b) O que continua esperando você, da 3.6.45

Nada disso mudou, e continua na tela *Demais atribuições → O que falta informar*:

1. o **Provimento 28/2018** da CGJ-MA (dispensa de testemunhas no registro tardio);
2. se a **FUNAI** e os **gêmeos** devem ou não contar o acervo;
3. os **canais** da FUNAI, do FERC/FERJ e do IBGE;
4. as **nove pendências de numeração** declaradas pela carga;
5. **usuário e senha do SIRC**, ou a decisão sobre o certificado A3;
6. o **INFODIP**, no TRE.

---

## Os passos

1. **Feche o sistema** no servidor.
2. **Faça o backup** — o de sempre, pelo próprio sistema.
3. Abra **Administrativo → Atualizar sistema** e escolha
   `CartorioGestao_3.6.46.cgu`.
4. Confira o **SHA-256** que a tela mostra contra o desta página.
5. Suba o sistema. **O banco migra sozinho.**

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| rodapé de qualquer tela | **3.6.46** |
| Registro Civil → Termos a escrever | **zero** — e não 244 |
| → Informações importadas | **244**, com o aviso de que não é lista de trabalho |
| → Modelos dos termos | o de **nascimento marcado como medido** no termo 8.369 |
| → um assento novo → Checklist | **cinco itens** num nascimento, **três** nos demais |
| impressão da folha | **três colunas**, e a de notas também no **verso** |

Se «Termos a escrever» ainda mostrar 244, a atualização não subiu — é o número de
antes do conserto.

---

## Uma nota sobre o tempo

Você instalou o `pytest-xdist` hoje. A bateria de testes que levava **38 minutos**
passou a levar **pouco mais de três**, usando os doze núcleos em vez de um.

Isso já rendeu na primeira vez em que rodou: o teste que pega rota sem tela
apontou a `rcpn_formulario` como órfã. Serial, esse aviso levaria meia hora para
chegar — e nesse meio-tempo eu já teria ido para outro assunto.

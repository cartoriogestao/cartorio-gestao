# Roteiro da 3.6.45 — o que aplicar, e o que decidir

*30/08/2026*

---

## Primeiro: **basta um arquivo**

Foram empacotadas sete versões na madrugada de 29 para 30/08 — da 3.6.39 à
3.6.45. **Você não precisa aplicar as sete.**

Cada pacote exige apenas a versão **3.3.0 ou superior** (`min_version: 3.3.0`), e
o servidor está na **3.6.15**. Aplique **só o último**:

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.45.cgu` |
| onde | `C:\Users\<usuario>\Downloads\CartorioGestao\` |
| tamanho | 2.045.505 bytes |
| SHA-256 | `57109261c042585d8547972ec8c634cfc80c413b770c9b750c8cd01b4cf9a7f1` |
| arquivos dentro | 447 |

Ele traz tudo o que as seis anteriores traziam.

**O banco migra sozinho ao subir** — as tabelas e colunas novas são criadas na
inicialização, e o dado antigo não é tocado. As colunas novas desta leva:
`gemeo_ordem` e `gemeo_irmao_id` em `rc_assentos`; e as tabelas `ex_fontes`,
`ex_anotacoes`, `ib_entregas`, `rc_funai`, `rr_processos`, `rr_consultas_crc`,
`rr_pecas`, `rr_andamento`, `rr_comunicacoes_353`.

---

## O que mudou, em ordem de utilidade para o balcão

### 1. Uma tela que diz o que a casa deve hoje

**Registro Civil → O que comunicar hoje.** Seis linhas, **nove destinos**, cinco
prazos — de um dia útil a trimestral. Antes, para saber o que venceu, eram sete
telas.

Ela **não comunica nada**: pergunta a cada módulo quantas estão esperando e leva
à tela que faz. E quando um módulo não sabe responder, ela diz **«não deu para
medir»** com o motivo — nunca zero.

### 2. As remessas e comunicações que faltavam

| | prazo | onde |
|---|---|---|
| **SIRC** | 1 dia útil (art. 225) | Registro Civil → Remessa do SIRC |
| **FUNAI** | imediatamente (art. 253, § 2º) | → Comunicação à FUNAI |
| **IBGE** — o registro do que foi **entregue** | dia 8, com multa (art. 224) | → Remessa do IBGE |

O SIRC leva **sete coisas**, e não só os registros: averbação, anotação e
retificação entram nele. A FUNAI tem **quatro casos** no acervo, três de 2026.

### 3. Retificação, restauração e suprimento do RCPN

**Registro Civil → Retificação e suprimento.** Arts. 348 a 355, lidos no PDF que
está na casa. Os três institutos são separados de propósito — juntá-los faria
escolher o caminho errado.

**O sistema recusa decidir sem a consulta à CRC** (art. 348, § 2º): ela é
*condição de validade da decisão*, e não zelo.

### 4. O que ficou pelo caminho

**Administrativo → Atendimento → O que ficou pelo caminho.** Nove fontes de atos
começados e não terminados, **medidas na hora** — escritura em lavratura,
prenotação sem ato, rascunho do RI, atendimento do balcão, usucapião, retificação
de área, habilitação, expediente e tarefa.

**Ato concluído sai da lista sozinho** — foi o que você relatou (a tarefa
concluída com o expediente ainda aberto), e é o que isso conserta.

A tela **molda o que fica e o que sai**: você liga, desliga e escolhe os dias por
fonte, num sábado, sem programador.

### 5. Três réguas do Registro Civil

**Registro tardio · Gêmeos · CPF nos assentos antigos** (art. 347).

---

## O que precisa da sua decisão

### a) O Provimento 28/2018 da CGJ-MA

O modelo de registro tardio desta casa traz impresso, **em toda folha**:
*«Dispensada a presença de testemunhas nos termos do Artigo 3º do Provimento
28/2018 – CGJ-MA»*.

O **art. 249, II** do Código de Normas diz que a regra é colher **duas
testemunhas**, com dispensa **num caso só**: registrando **menor de 12 anos**
*e* com **DNV apresentada** — cumulativos.

**Não li o Provimento 28/2018**, e por isso não afirmo que ele não amplie a
dispensa. O sistema hoje **calcula** pelo Código de Normas e diz por quê. Se você
souber que o Provimento amplia, a régua muda num lugar só —
`rc_registro_tardio.dispensa_testemunhas`.

> Um papel que afirma a dispensa sempre faz o balcão deixar de colher testemunha
> onde ela é obrigatória, e é o declarante quem assina «sob as penas da lei».

### b) Duas listas que decidi contar o acervo, e podem ser sua decisão

**A FUNAI conta os nascimentos indígenas do acervo.** Raciocínio: o RANI é **o
documento da pessoa**, e não uma remessa estatística — se não foi feito, a criança
segue sem ele, e o tempo não apaga isso. São quatro casos, três de 2026.

**Os gêmeos contam os assentos antigos sem ordem de nascimento.** A ordem é
requisito do assento (art. 233, III), e a falta é real mesmo em 1990. Mas ali o
caminho é a **retificação** (art. 352, I), e não editar o campo — a tela diz isso.

Se você entender que uma delas não deve listar o acervo, é uma linha em
`tests/test_o_acervo_nao_vira_atraso.py` e o filtro no módulo.

### c) Os endereços e canais

- **FUNAI** — por onde a comunicação sai (malote, e-mail, ofício em mão)?
- **FERC e FERJ** — o canal das comunicações do art. 353.
- **IBGE** — o sistema já sabe gerar o mapa; falta dizer por onde ele vai.

### d) O que já estava pendente, e continua

1. o próximo número do **Registro de Protestos** e do **Registro de Pagamentos**;
2. a letra da **posição 566** do retorno da CRA, para apresentante novo;
3. o **Livro 6 de Apontamento**, aberto em 2024 e nunca usado;
4. o **próximo número do casamento** — a carga semearia 1012, o E-Ofício diz 39;
5. o próximo número do **B-Auxiliar, C-Auxiliar e D**;
6. **usuário e senha do SIRC**, ou a decisão sobre o certificado A3;
7. o **INFODIP**, no TRE.

Elas estão em *Demais atribuições → O que falta informar* — **e a carga já as
declarou: são nove no servidor**.

---

## O que este roteiro corrige do que estava escrito antes

**A carga do acervo já rodou.** O `CLAUDE.md` dizia que não, com os números de
27/08. Medido em 30/08, só leitura, no banco do servidor:

| | |
|---|---|
| assentos do RCPN · pessoas · atos | **244** · **1.084** · **244** |
| títulos de protesto | **1.366** |
| RCPJ/RTD · Livro 3 | **72** · **14** |
| selos no razão | **26.134** |
| pendências de numeração declaradas | **9** |

Se você não rodou a carga, ela rodou por outro caminho — e vale conferir a
**tela de numeração** antes de o balcão voltar a lavrar, porque é dela que sai o
próximo número de cada série.

---

## Os passos

1. **Feche o sistema** no servidor.
2. **Faça o backup** — o de sempre, pelo próprio sistema.
3. Abra **Administrativo → Atualizar sistema** e escolha
   `CartorioGestao_3.6.45.cgu`.
4. Confira o **SHA-256** que a tela mostra contra o desta página.
5. Suba o sistema. **O banco migra sozinho** — leva alguns segundos.
6. Abra **Registro Civil → O que comunicar hoje**. Se alguma linha disser «não
   deu para medir», me diga o que ela escreveu: é a única coisa desta leva que
   não consigo prever daqui.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| rodapé de qualquer tela | **3.6.45** |
| Registro Civil (menu) | **três seções**: O balcão · Assento já lavrado · Comunicações e remessas |
| → O que comunicar hoje | **6 obrigações, 9 destinos** |
| → Remessa do SIRC | **Nada esperando remessa** — e não 243 |
| → Termos a escrever | **0 a escrever de verdade**, de 244 sem termo |
| → Carga da CRC | **243 a carregar**, com a frase dizendo que isso é o esperado |

Se o SIRC mostrar 243 em vez de zero, a atualização não subiu — é o número de
antes do conserto.

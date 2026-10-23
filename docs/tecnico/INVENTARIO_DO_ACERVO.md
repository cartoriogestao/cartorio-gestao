# O que o E-Ofício guardava, e onde isso está hoje

Medido em **27/08/2026**, cruzando as **229 tabelas** do acervo com o banco de
produção do sistema novo.

O oficial perguntou se valia um tour pelo E-Ofício para achar soluções a
incrementar. Vale — mas não pelo código dele: **pelo que ele guardou**. O código
diz o que o programa *podia* fazer; o acervo diz o que a casa *fez*.

E este projeto já pagou duas vezes por confiar no primeiro em vez do segundo.

---

## O método, e o erro que ele quase me fez cometer

A primeira passada foi burra: procurei o nome de cada tabela do acervo dentro
dos `.py` do projeto, e concluí que **171 tabelas, com 433 mil linhas, não eram
lidas por ninguém**.

Estava errado, e o cruzamento com o banco de produção mostrou por quê: os
importadores antigos — `ri_import`, `notas_import`, `caixa_import` — leem
**JSONL exportado**, e não as tabelas do acervo. O nome não aparece no código, e
o dado está lá dentro do sistema.

> **Procurar o nome no código mede o código, e não o dado.** O que responde
> "isto está no sistema?" é contar as duas pontas.

---

## O que ESTÁ no sistema, conferido linha a linha

| No acervo | No sistema | O quê |
|---:|---:|---|
| 50.054 | **50.054** | CNIB — ordens de indisponibilidade |
| 50.054 | **50.054** | CNIB — pessoas |
| 21.360 | **21.348** | Protocolo geral |
| 13.209 | **13.212** | Reconhecimentos de firma |
| 4.051 | **3.992** | Partes das matrículas |
| 3.689 | **3.667** | Fichas digitalizadas do RI |
| 3.539 | **3.540** | Autenticações |

Onde o sistema tem **mais** que o acervo, a diferença é o que a casa lançou
depois da exportação. Onde tem menos, é o que os importadores rejeitaram na
época, com motivo escrito.

**Metade do movimento desta casa — o reconhecimento de firma — está inteiro
dentro do sistema novo.** Isso não era óbvio antes de contar.

---

## O que NÃO está, e por quê

### 1. O que depende da carga que ainda não rodou

| No acervo | No sistema | O quê |
|---:|---:|---|
| 20.800 | 0 | Livro de Apontamento do Protesto |
| 1.618 | 0 | Avisos de intimação |
| 1.086 | 0 | Editais |
| 1.366 títulos | 0 | Protesto |
| 244 assentos | 0 | Registro Civil |

**Não é buraco de programa: é o passo 4 do roteiro**, que ainda não foi
executado no servidor. A carga existe, é repetível e foi ensaiada.

### 2. O razão dos selos — e este é um buraco de verdade

| No acervo | No sistema | O quê |
|---:|---:|---|
| **26.130** | **0** | `tbSeloIndividual` → `sd_selos` |

**Nenhuma carga traz os selos históricos.** A carga do Protesto grava o número
do selo *dentro do ato* (`pt_atos.selo`), o que é certo; mas o **razão** —
`sd_selos`, a tabela que responde "este selo já foi usado, e em quê?" — começa
vazio.

Isso tem consequência prática: `registrar_selo_obtido_a_mao` recusa selo
repetido comparando contra o razão. Com o razão vazio, um selo de 2023 pode ser
digitado hoje como novo e **nada recusa**.

> Foi de `tbSeloIndividual` que saíram a receita de custas do RCPN, os 34
> caminhos do selador e o controle de papel. É a tabela mais informativa do
> acervo, e é a que menos está no sistema.

### 3. O que é de outro sistema, e fica onde está

| No acervo | O quê |
|---:|---|
| 70.533 | `tbAuditor` — a auditoria do E-Ofício |
| 7.441 | `tbUpdateC11` — as atualizações do programa antigo |
| 5.638 + 5.444 | duas tabelas de municípios |
| 4.270 | `tbAcesso` — os acessos ao E-Ofício |

Trazer o log de auditoria de outro programa para dentro deste misturaria dois
rastros com regras diferentes. O acervo continua consultável, e é onde essas
perguntas se respondem.

---

## O que este inventário achou de aproveitável

**Já aproveitado hoje**: o controle de folhas de segurança
(`tbPapelMoedaRCPN`, 510 folhas) — que apareceu por acaso, medindo o selo, e
agora tem módulo, tela e carga.

**O que sobra, em ordem de tamanho:**

1. **Trazer os 26.130 selos para `sd_selos`** — fecha a trava do selo repetido e
   dá ao sistema a memória de tudo o que esta casa selou em seis anos.
2. **`tbProtocoloGeralCustas` (32.424) e `tbProtocoloGeralATO` (24.925)** — o
   que cada protocolo custou e que ato saiu dele. O protocolo veio; o que ele
   custou, não.
3. **`tbFirmaSelosUsados` (1.697) e `tbFirma_Cartao_Autografo_Selos` (2.151)** —
   os selos das firmas, ligados ao cartão.
4. **`tbIO_Dia` (1.519)** — a abertura e o fechamento do dia, que é o
   encerramento diário que o núcleo já modela.

Nenhuma delas trava o balcão hoje. A primeira é a que mais rende, e é a que eu
faria primeiro.

---

## Uma coisa que o inventário confirmou

O acervo tem **229 tabelas com pelo menos uma linha** — nenhuma vazia. Isso quer
dizer que o E-Ofício era usado inteiro, e que cada tabela ali é uma pergunta que
alguém já respondeu nesta casa.

**Quando o sistema novo não souber algo, o acervo provavelmente sabe.**

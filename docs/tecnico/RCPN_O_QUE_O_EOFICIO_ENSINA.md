# O RCPN do E-Ofício como referência: o que dá para aproveitar

*29/08/2026 — resposta ao pedido do oficial:*

> «conseguimos olhar o código do e-ofício para o rcpn e incorporar as funções
> usando ele como referência para agilizar o processo de amadurecimento do
> rcpn?»

**Resposta curta: o código, não. Os modelos, sim — e eles são melhores que o
código.**

---

## O que se procurou, e o que se achou

`C:\ARPNET` tem **30 GB**. Fui atrás do código:

| onde | o que é |
|---|---|
| `C11\C11.exe` (23 MB, 2023) e `e-oficio-ma.exe` (31 MB, dez/2025) | **binários compilados**. Não há fonte. |
| `C11\Fontes` | **tipos de letra** — Times New Roman, códigos de barras. O nome engana. |
| `C11\RPT` — 178 relatórios do Crystal Reports | todos de **Protesto e Caixa**. **Nenhum do Registro Civil.** |
| `C11\CRC` e `C11\Remessa` | **vazias** |

> **Decompilar o executável está fora de questão**, e não por dificuldade: é
> software de terceiro, licenciado à serventia para usar. O que a casa pode ler
> livremente é **o que é dela** — os dados e os textos que ela mesma produziu.

## E é aí que está o achado

**O RCPN do E-Ofício não imprime por relatório: ele guarda os modelos no
banco.** `tbModelosRCPN` tem **13 modelos**, em RTF, com o texto inteiro — e o
acervo é da casa.

| # | modelo | o que é | temos? |
|---|---|---|---|
| 1 | Certidão de Nascimento 1ª via | certidão | **sim**, montada dos campos |
| 15 | Certidão de Nascimento 2ª via | certidão | **sim** |
| 2 | Certidão de inteiro teor | certidão | **sim** |
| 10 | Certidão de Casamento | certidão | **sim** |
| 12 | Certidão de Óbito | certidão | **sim** |
| 13 | Casamento Religioso | certidão | **sim** |
| **11** | **Termo** (nascimento) | **o texto que se escreve no livro** | **NÃO** |
| **14** | **Termo** (óbito) | **idem** | **NÃO** |
| **8** | **Termo de Gêmeos** | registro de nascimento de gêmeos | **NÃO** |
| **4** | **Registro Tardio** | art. 46 da LRP | **NÃO** |
| **7** | **Termo de Alegação de Paternidade** | Lei 8.560/1992 | **NÃO** |
| **3** | Investigação de paternidade — modelo oficial do juiz | idem | **NÃO** |
| **9** | **Comunicação de Casamento para o Registro de Nascimento** | a anotação do art. 106 da LRP | **NÃO** |

**Sete dos treze não existem no nosso sistema.** E o mais importante deles é o
**termo** — o texto que vai no livro. Este projeto construiu a certidão
(`rc_certidao.py`, montada dos campos, no modelo do CNJ) e **não construiu o
termo**, porque os 244 assentos do acervo vieram **sem teor nenhum**: as três
colunas de texto estão vazias nas três tabelas de origem.

Agora se sabe por quê: **o E-Ofício não guardava o teor — ele o montava do
modelo na hora de imprimir.** O termo existia; só não estava no banco.

---

## O termo de nascimento, como esta casa o escreve

Extraído do modelo #11, com os campos no lugar:

> **REGISTRO DE NASCIMENTO** — Termo: `@registro` Livro: `@livro` Folha:
> `@folha`
>
> Aos `@dataregistroextensoCN`, neste Município de Cidade Exemplo, Estado do
> Maranhão, neste ofício, compareceu o(a) Sr.(a) `@nomedeclarante1`, […]
> apresentou a DNV n.º `@declaracaonascidovivo`, e declarou que no dia
> `@datanascimentoextensoCN`, às `@horanascimento`, em `@nomelocalnascimento`
> […] nasceu uma criança do sexo `@sexonascido`, cor `@cornascido`, que recebeu
> o nome de: "`@NOMENASCIDO`", sendo filho(a) de `@nomefiliacao1` […] e de
> `@nomefiliacao2` […], **tendo a mãe, na ocasião do parto, `@idadefiliacao1`
> anos de idade**, tendo como avós paternos: `@avosfiliacao2` e maternos:
> `@avosfiliacao1`. **A naturalidade declarada é de
> `@municipio_registro_nascimento`, na forma do art. 54, § 4º, da Lei Federal
> n.º 6.015/1973.** […] Lido e achado conforme, o(a) declarante assina. Eu,
> `@registrador`, `@funcaoregistrador`, dou fé e assino. Matrícula
> `@matriculanascido`.

Três coisas que este texto ensina e que eu não teria escrito sozinho:

1. **a idade da mãe no parto entra no termo** — e é o mesmo dado que a remessa
   do IBGE cobra;
2. **a naturalidade declarada cita o art. 54, § 4º** — a faculdade de declarar
   como naturalidade o município de residência da mãe;
3. **os avós paternos são `@avosfiliacao2` e os maternos `@avosfiliacao1`** —
   o que confirma, pelo lado do texto, a numeração de filiação que este projeto
   mediu no acervo em 28/08.

---

## O vocabulário: 155 campos, medidos

Os treze modelos usam **155 campos distintos**, no formato `@nome`. Eles são,
juntos, **a lista de tudo que o RCPN precisa guardar** — e é uma lista medida,
não imaginada.

Os que o nosso sistema **ainda não tem**, e o termo cobra:

| campo do E-Ofício | o que é |
|---|---|
| `@idadefiliacao1` / `@idadefiliacao2` | **a idade da mãe e do pai no parto** |
| `@avosfiliacao1` / `@avosfiliacao2` | os avós, já como texto pronto |
| `@nacionalidadedeclarante1`, `@profissaodeclarante1`, `@rgdeclarante1` | a qualificação do declarante |
| `@enderecolocalnascimento`, `@nomelocalnascimento` | onde a criança nasceu |
| `@cornascido` | a cor, que o SIRC e o IBGE cobram |
| `@possuigemeos` | e o modelo próprio de gêmeos |
| `@tituloeleitorfalecido`, `@possuibens`, `@causamorte`, `@atestanteprimario` | os do óbito, que o INFODIP e o SIRC cobram |
| `@novonomeconjuge1` / `@novonomeconjuge2` | o nome que cada cônjuge passou a usar |
| `@regimebens` | o regime |
| `@selo` | o selo dentro do termo |

O vocabulário inteiro, com quantos usos cada um tem e em que modelos, está em
`FONTES_EXTERNAS/modelos_rcpn_eoficio/`, junto dos treze textos extraídos e do
extrator (`extrair_rtf.py`).

---

## Dois defeitos que a extração achou de passagem

**Os modelos estão com dois oficiais diferentes.** O modelo #11 (termo de
nascimento) traz **OFICIAL — Tabelião e Oficial de Registro**;
o modelo #9 (comunicação de casamento) ainda traz **TITULAR ANTERIOR — Tabeliã e Registradora Interina**, com endereço e telefone antigos, e
até um CEP diferente (65.289-000 contra 65.936-000).

> **É o «carimbo que mente» outra vez.** Ao trazer estes textos para cá, o nome
> de quem responde pela serventia **não se copia**: sai da mesma regra do
> cartão de autógrafo e da certidão do RI — `substituta or registrador` —, que
> mora num lugar só. Copiar o cabeçalho junto traria o oficial antigo de volta
> para dentro do sistema novo.

**E o meu extrator de RTF errou duas vezes antes de acertar**, o que vale
registrar porque é a mesma família de engano:

- a primeira versão apagava os grupos com expressão regular, e RTF é **árvore
  aninhada** — saiu vazio;
- a segunda empilhava o silêncio **duas vezes** no mesmo grupo (`{\*\panose}`
  casa com as duas regras) e desempilhava uma só: a pilha nunca esvaziava, e
  **todos os treze modelos saíram com zero caracteres**.

Zero em todos é sinal de defeito do leitor, e não de arquivos vazios. A terceira
versão guarda **uma profundidade só** — onde o silêncio começou — e o
aninhamento deixa de importar.

---

## O que eu proponho, agora que há precedente

1. **Trazer os sete modelos que faltam** para o catálogo de modelos da casa
   (`modelos_da_casa.py`, do relato #28), com o cabeçalho **substituído pela
   regra viva** de quem responde pela serventia.
2. **Acrescentar ao assento os campos que o termo cobra** e que hoje não
   existem — a idade dos genitores no parto à frente, porque ela está no termo
   **e** na remessa do IBGE.
3. **Construir a comunicação de casamento ao registro de nascimento** (art. 106
   da LRP): é ato de anotação que a casa deve, tem modelo pronto, e o nosso
   `TIPOS_ATO` já prevê `ANOTACAO`.
4. **Construir o registro tardio e o termo de gêmeos**, que são espécies de
   nascimento com forma própria — e o acervo tem `bitRegistroTardio` e
   `bitGemeos`/`intQuantidadeGemeos` para provar que a casa os usa.
5. **Depois** o SIRC, a CRC, o INFODIP e a Junta Militar, que já estão
   pesquisados em `RCPN_PESQUISA_DAS_CENTRAIS.md`.

**A ordem é essa de propósito**: o termo é o que o livro precisa, e as centrais
recebem o que o termo registrou. Construir a remessa antes do termo seria mandar
para fora um dado que a casa ainda não sabe escrever dentro.

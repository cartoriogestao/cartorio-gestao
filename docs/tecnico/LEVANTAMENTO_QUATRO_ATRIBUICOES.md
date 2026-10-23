# Levantamento — RCPN, Protesto, RCPJ e RTD, o selador, e o que fazer com isso

Escrito em 20/08/2026, lendo três fontes: as **78 recomendações** da inspeção ordinária de
12/08/2026, o **esquema completo do E-Ofício** (411 tabelas, 4.944 colunas, 228 com dados e
544.728 linhas) e o **código do sistema atual**.

> **O que este documento é.** Um levantamento, não um projeto. Cada afirmação abaixo tem uma
> tabela, uma coluna ou uma recomendação por trás. Onde eu não sei, está escrito que não sei.

---

## 1. A descoberta que muda o desenho: as seis atribuições são uma só máquina

O E-Ofício numera as atribuições, e vale adotar exatamente os mesmos códigos:

| Cód. | Atribuição | Atos catalogados |
|---|---|---|
| 1 | Notas | 18 |
| 2 | Protesto | 10 |
| 3 | Registro Civil das Pessoas Jurídicas | 15 |
| 4 | Registro de Títulos e Documentos | 9 |
| 5 | Registro de Imóveis | 16 |
| 6 | Registro Civil das Pessoas Naturais | 5 |

São **73 tipos de ato**, cada um com o seu tipo de selo. Dois estão desativados: *Apostila de
Haia* no Protesto e *Certidão Unificada de Protesto*.

E aqui está o ponto: **a inspeção pede a mesma coisa às quatro atribuições novas.**

| Exigência | RCPN | Protesto | RCPJ | RTD |
|---|---|---|---|---|
| Inutilizar folhas/versos em branco | — | ✔ | ✔ | ✔ |
| Assinatura do delegatário ao final de cada ato | ✔ | | ✔ | |
| Termos de abertura e encerramento do livro | ✔ | ✔ | | |
| Rubrica das folhas | | ✔ | | |
| Divisão do livro em campos (notas, averbações, retificações) | ✔ | | | |
| Encerramento diário do Livro de Protocolo | | ✔ | ✔ | |
| Selo, emolumentos, destinações e gratuidade padronizados | ✔ | ✔ | | |
| Continuidade da numeração ao migrar do livro físico | ✔ | | | |

> **Correção de 20/08, depois de escrever os testes.** A primeira versão desta tabela
> marcava a inutilização de folhas em branco também no RCPN. Está errado: a inspeção cobrou
> inutilização no Protesto, no RCPJ e no RTD, e **não** no RCPN — ali ela cobrou a divisão
> tripartite do assento e o acondicionamento dos registros de óbito. A regra de escrituração
> sem claros continua valendo para o RCPN por norma; o que não existe é apontamento da
> inspeção. Deixo a correção à vista em vez de reescrever a tabela em silêncio.

Nada disso é novo para o sistema. **Já está construído e testado no Tabelionato de Notas:**
`notas_livro.py` (livro, folha, termo contínuo por série, livro cheio abre o seguinte),
`notas_inutilizacao.py` (a face que sobra sai impressa já inutilizada) e o `fecho_do_ato`
(assinatura congelada no ato).

> **A conclusão de projeto.** Construir quatro módulos novos, cada um com a sua cópia da
> numeração de livro, seria fabricar quatro versões divergentes do código mais difícil do
> sistema. O erro de 18/08 — numeração contada por volume em vez de por serventia — mostra o
> que uma divergência dessas custa. **O caminho é extrair um núcleo comum e cada atribuição
> declarar as suas séries.**

O E-Ofício, aliás, fez exatamente isso onde pôde: RTD e RCPJ **compartilham** as tabelas
`livroTDPJ` e `tbTipoLivros_TDPJ`, e o controlador `tbTD_Propriedade` conta os dois.

---

## 2. O selador — agora sabemos como funciona, e é menos misterioso do que parecia

Três achados, em ordem de importância.

**Primeiro: existe uma tabela de configuração do selador, e ela tem exatamente três colunas.**

```
tbSeladorConfiguracao( strUrlSelador, strUsername, strPassword )
```

Está **vazia** nesta exportação — as credenciais não saíram, ou foram limpas antes. Mas as três
colunas dizem o essencial: **o selador é um endereço HTTP com usuário e senha.**

**Segundo: cada serviço tem o seu caminho no selador.** A coluna `tbServico.strURL_Selador`
guarda um caminho relativo. Dos 1.317 serviços, **60 têm caminho preenchido**, e todos são do
RTD/RCPJ:

```
37x  /selo/rtdpj/ato-declarado/integral/com-valor
 8x  /selo/rtdpj/ato-declarado/integral/sem-valor
 8x  /selo/rtdpj/busca-ate-dez-anos
 4x  /selo/rtdpj/ato-declarado/resumido/sem-valor
 3x  /selo/rtdpj/atos-em-geral
```

> **Isto responde à sua pergunta com uma ressalva importante.** O E-Ofício selava
> automaticamente — mas, **nesta serventia, só no RTD e no RCPJ**. As outras atribuições ficaram
> com o selo obtido à mão, no portal. Então "fazer como o E-Ofício faz" é um alvo real e já
> observado, e ao mesmo tempo é um alvo que ninguém aqui exercitou fora do RTD/PJ.

**Terceiro: `tbSeloIndividual`, com 26.130 linhas e 42 colunas, é a planta do ciclo de vida
do selo.** As colunas contam a história sozinhas:

| Grupo de colunas | O que revela |
|---|---|
| `strSelo`, `intTipoSelo`, `intCodigoAto`, `intCodigoServico`, `intCodigoMotivo` | o selo e a sua classificação |
| `bitReservado`, `strReserva_Userid`, `dtmReserva`, `bitUtilizado` | **reserva antes do uso** — o selo é separado para um usuário e só depois consumido |
| `intIDAto`, `strProtocoloGeral`, `strProtocolo_Protesto`, `LivroRegistro`, `FolhaRegistro` | a amarração ao ato, ao protocolo e à folha do livro |
| `curV_Selo`, `curValorTotal`, `bitIsento` | valor e isenção |
| `strValidador`, `strvalorQRCode`, `bitImgQRCodeGerada`, `strURLAto`, `strTextoSelo` | o QR, o validador e o texto que sai impresso |
| `bitPendenteEnvioTJ`, `bitLiberadoParaEnvioTJ`, `bitEnviadoTJ`, `dtmDataEnviadoTJ`, `memJson` | **uma fila de envio ao Tribunal**, com o payload guardado |
| `bitSeloInutilizado`, `bitSeloCancelado`, `bitmarcadocancelar` | inutilização e cancelamento |
| `bitRetificadoTJ`, `strSeloRetificacaoTJ` | retificação de selo já enviado |

> **A dúvida honesta que sobra.** A existência de `bitPendenteEnvioTJ` / `bitEnviadoTJ` admite
> duas leituras: ou o selo é **obtido** do Tribunal na hora do ato e o "envio" é a prestação de
> contas depois; ou a serventia recebe **faixas de selos** e informa o uso depois. As colunas
> `bitReservado` / `dtmReserva` puxam para a segunda leitura. **Não vou projetar sem saber
> qual.** Para decidir bastam duas coisas: os dados de `tbSeloIndividual` (40 MB, dá para
> trazer) e o ato normativo do TJMA sobre o selo eletrônico.

**Os fundos estão confirmados**, e explicam a linha de emolumentos que você vê nos selos:

| Sigla | Fundo | % |
|---|---|---|
| FERC | Fundo Especial de Modernização e Reaparelhamento do Judiciário | 3 |
| FEMP | Fundo Especial do Pessoa Exemplo | 4 |
| FADP | Fundo de Aparelhamento da Defensoria Pública do Maranhão | 4 |
| ISS | Imposto Sobre Serviços | 5 |
| FERRFIS | Fundo Especial Registral de Regularização Fundiária de Interesse Social | 1 |

E há **11 tipos de selo** (Atos Gerais, Atos Gratuitos, Autenticações, Reconhecimento de Firma,
Ato Gratuito Judicial, Ato Oneroso Judicial, Firma-Veículo, Abertura de Firma, Certidão,
Firma-Financeiro, **Selo Eletrônico**) — e 1.301 dos 1.317 serviços usam o **Selo Eletrônico**.

Há também **papel de segurança** a controlar, com 11 fornecedores catalogados e um estoque
próprio no RCPN (`tbPapelMoedaRCPN`, 510 linhas, com código, série, remessa e "utilizado").

---

## 3. RCPN — a maior das quatro, e a que tem o acervo mais rico

**14 recomendações da inspeção**, das quais 6 CRÍTICAS e 2 com prazo zero (imediato).

### O que existe de acervo

| Tabela | Linhas |
|---|---|
| `tbRegistroNascimento` (54 colunas) | 193 |
| `tbRegistroCasamento` (94 colunas) | 20 |
| `tbRegistroObito` (71 colunas) | 31 |
| `tbCertidaoRCPN` | 147 |
| `tbTeor_RCPN` | 67 |
| `tbTestemunhaRCPN` | 450 |
| `tbPapelMoedaRCPN` | 510 |
| `tbModelosRCPN` | 13 |
| `tbRCPN_Averbacao` | 1 |

### O achado que fecha o círculo com a inspeção

`tbPropriedadeRCPN` guarda **o estado exato dos livros físicos**, e ele confere, um a um, com o
que a inspeção apontou:

| Livro | Estado no E-Ofício | A inspeção diz |
|---|---|---|
| Nascimento | **Livro 24**, registro 19552, folha 166 | "Livros **A-24**" |
| Casamento | **Livro 4**, registro 39, folha 39 | "e **B-04**" |
| Óbito | **Livro 5**, registro 1976, folha 275 | "Livro **C-05**" |
| Proclamas | **Livro 3**, registro 1358, folha 126 | "Livro **D-03**" |
| Casamento auxiliar | Livro 2 | "Livros **B-Auxiliar** e C-Auxiliar" |
| Óbito C-Auxiliar | Livro 2, registro 12 | idem |
| Livro E | Livro 2, folha 39, 150 folhas | — |

Todos com **300 folhas** e **1 registro por folha**. E há `bitPermiteEditarAposSelar: False` —
o E-Ofício travava a edição depois de selar.

> **O que isso significa na prática.** A recomendação "encerrar os Livros B-Auxiliar e
> C-Auxiliar e **migrar atos futuros para sistema informatizado, mantendo a continuidade da
> numeração**" é executável com precisão: os números de partida são estes, vindos do sistema
> antigo, e não de estimativa.

Também aparece o caminho da carga do IBGE, num Proton Drive: `.../2. RCPN/CARGAS IBEG/2º
TRIMESTRES 2026`. Ou seja, a obrigação trimestral do IBGE já existe como rotina manual.

### O que o RCPN exige que nenhuma outra atribuição exige

- **SIRC** — carga de nascimentos, casamentos e óbitos, com passivo histórico de
  janeiro/2016 a novembro/2017 a sanear, e os termos 19519 e 19521 pendentes.
- **CRC** — 5 lotes de legados pendentes, e rotina de prazos.
- **Unidade Interligada** — comunicação formal do andamento.
- **DNV** (Declaração de Nascido Vivo) e a hipótese de DNV inexistente.
- **Matrícula de 32 dígitos** do registro civil (`strNumeroMatricula`).
- **Paternidade** — Lei 8.560: diligenciar a genitora e lavrar o termo.
- **Registro tardio**, **gêmeos**, **natimorto**.
- **Divisão tripartite do livro** — cada assento com campo próprio para nota, averbação e
  retificação, **inclusive no verso**.

---

## 4. Protesto — a que tem o maior risco jurídico

**10 recomendações**, 5 CRÍTICAS, prazos de 15 e 30 dias.

### O que existe de acervo

| Tabela | Linhas | O que é |
|---|---|---|
| `tbLivroApontamento` | **20.800** | o Livro de Apontamento: livro, folha, ordem, sequência, sacado, credor, espécie, valor, vencimento, apresentante |
| `tbAvisoProtesto` | 1.370 | **176 colunas** — a vida inteira de cada título |
| `tbProtesto_RO` | 1.329 | o **Registro de Ocorrências** por protocolo |
| `tbEdital` | 1.086 | editais, com data de publicação |
| `tbProtesto_Motivo` | 1.132 | motivos, com o texto informativo de cada um |
| `tbProtocoloProtesto` | 435 | o controle diário do protocolo |
| `tbProtesto_PG` | 341 | ligação com o protocolo geral |
| `tbProtesto_Certidao` | 65 | certidões |
| `tbAberturaProtesto` | 26 | abertura do dia |
| `tbLivro_Registro_Pagamento` | 1 | **o Livro 1, ordem 826 a 2145, 11 folhas, de 17/02/2022 a 12/08/2026** |

`tbAvisoProtesto` tem **um campo de selo para cada etapa** — distribuição, intimação,
apontamento, certidão, cancelamento, arquivamento, diligência, intimação por edital, certidão
de cancelamento — e, para cada, o valor com FERC, MP, DP e FERRFIS separados. É a prova de que
no protesto **o selo não é um por ato: é um por etapa**.

E `tbSetupSistema` tem as travas de validação de selo por etapa, ligadas assim nesta serventia:
distribuição **não** valida; intimação, protesto, certidão, arquivamento e diligência **validam**.

### As 19 ocorrências, que são o vocabulário do protesto

Pago · Protestado · Retirado · Sustado · Devolvido por irregularidade sem custas · Devolvido
por irregularidade com custas · Liquidação em condicional · Título aceito · Edital · Protesto
do banco cancelado · Protesto já efetuado · Protesto por edital · Retirada por edital ·
Protesto de terceiro cancelado · Desistência por liquidação bancária · Sustado definitivo · 2ª
via do instrumento · Cancelamento já efetuado · Cancelamento não efetuado.

Cada uma diz se **gera selo** e se **entra na SDT**, e traz a quantidade de arquivamento.

### O que a inspeção cobra e o sistema terá de garantir

- **O tríduo legal**, controlado automaticamente, impedindo lavratura fora do termo final.
- **Prazos e formalidades das intimações**, inclusive por edital.
- **Tipo e motivo individualizados** — parar de usar motivo genérico.
- **Pagamentos registrados no campo Ocorrências do Livro de Protocolo**, tempestivamente.
- **Perfil de acesso próprio** para o responsável, vedado o uso de credencial de terceiro.
- Termos de abertura e encerramento, rubricas, e inutilização de versos.

---

## 5. RCPJ e RTD — quase sem acervo, e por isso as mais rápidas

**RCPJ: 3 recomendações. RTD: 1.** E as duas dividem a mesma estrutura de livros.

`tbTD_Propriedade` dá o estado atual dos dois, com o texto legal de cada livro:

| | RTD | RCPJ |
|---|---|---|
| Contador de registros | **1.508** | **372** |
| Livro atual | 2 | 4 |
| Protocolo | 1.275 | 1.273 |
| Folhas por livro | 300 | 300 |
| Registros por página | 1 | 1 |
| Usa verso | sim | sim |
| Averbação consome protocolo | **sim** | **não** |

**Os livros, com a fundamentação que o próprio E-Ofício guardou:**

- **RCPJ Livro A** — contratos, atos constitutivos, estatutos e compromissos de sociedades
  civis, religiosas, pias, morais, científicas ou literárias; fundações e associações de
  utilidade pública; sociedades civis em forma comercial, salvo anônimas; atos constitutivos e
  estatutos de partidos políticos.
- **RCPJ Livro B** — matrícula de oficinas impressoras, jornais, periódicos, empresas de
  radiodifusão e agências de notícias.
- **RTD Livro B** — trasladação integral de títulos e documentos.
- **RTD Livro C** — inscrição por extração, para efeitos contra terceiros e autenticação de data.
- **RTD Livro F** — registro facultativo para conservação (art. 127, VII e art. 127-A).

Há dados em `tbRegistroTD` (13,8 MB de exportação) e `tbTD_Certidao` (2 MB) — ainda não abri.

> **Ressalva a conferir.** A inspeção fala em "Livro **B-7**" do RTD, e o controlador diz
> `intLivroAtual_RTD: 2`. Pode ser que o 2 seja índice de tipo de livro e não volume. Preciso
> abrir `livroTDPJ` para desempatar.

---

## 6. Uma atribuição que o sistema já tem e ainda não cobre: o Livro 3 do RI

`tbRI_Auxiliar` (7,75 MB), `LivroAuxiliar` (14 linhas) e `tbRI_Modelo_RA` mostram o **Registro
Auxiliar** — Livro 3 do Registro de Imóveis, com título, tipo, valor de compra e venda, forma
de pagamento, parcelas, prazo, vencimentos, juros, garantia, condições e CNM.

O módulo de RI do sistema **não tem tela para isso**. E a tabela de numeração já traz o livro 3
com 1.650 em uso. É uma lacuna dentro de uma atribuição que já consideramos pronta.

---

## 7. O que eu ainda não sei, e como saberia

| Dúvida | Como resolver |
|---|---|
| O selador entrega selo na hora, ou a serventia recebe faixas? | trazer `tbSeloIndividual.jsonl` (40 MB) e ler o ciclo real; e o ato normativo do TJMA |
| Qual é a URL e como se autentica | a configuração está vazia no acervo — está no portal do TJMA, ou com quem instalou o E-Ofício |
| O formato exato do payload | `memJson` de `tbSeloIndividual` guarda o que foi enviado |
| "Livro B-7" do RTD × `intLivroAtual_RTD: 2` | abrir `livroTDPJ.jsonl` |
| O que há em `tbCN_Generica` (1.482 linhas, 49 MB) | tem `intAtribuicao` e `bitATOSelado` — parece certidão/nota genérica de várias atribuições |
| Os teores e modelos de cada atribuição | `tbModelosRCPN` (9,7 MB), `tbTeor_RCPN` (33 MB), `tbTipoEscritura`, `TipoAverbacao` |

> **Nada disso é impedimento para começar.** O núcleo comum — livro, folha, termo, inutilização,
> fecho, protocolo — não depende de nenhuma dessas respostas. O selador depende, e é por isso
> que ele não pode ser o primeiro passo.

---

## 8. O plano que eu proponho

### Fase 1 — o núcleo (não entrega tela nova, e é o que faz as outras quatro caberem)

1. Extrair de `notas_livro.py` um **núcleo de livro** genérico: série, volume, folha, verso,
   ordem, termo contínuo, abertura, encerramento, livro cheio, numeração por serventia.
2. Generalizar a **inutilização de folha em branco** para qualquer atribuição — é exigência da
   inspeção nas quatro.
3. Um **cadastro de atos** com as 73 entradas do E-Ofício: código, atribuição, tipo de selo,
   código da tabela do TJMA, liberado ou não.
4. Um **motor de emolumentos** com os cinco fundos e as vigências, calculando a linha que hoje
   se cola à mão.
5. **Encerramento diário do protocolo**, exigido em Protesto e RCPJ.
6. Fechar o backlog de defeitos que toca o núcleo — prenotação que não se amarra ao ato,
   `conferido_por`, o selo por Ctrl+V, o rascunho de ato sem consumir número.

### Fase 2 — Protesto

Maior risco jurídico: tríduo, intimações, edital, prescrição, efeito suspensivo. Acervo rico
para importar e conferir. Dez recomendações, cinco críticas.

### Fase 3 — RCPN

A maior em volume de exigência, e a que depende de coisas de fora: SIRC, CRC, IBGE, Unidade
Interligada. Faz sentido depois do Protesto, quando o núcleo já estiver exercitado.

### Fase 4 — RCPJ e RTD

Compartilham livros e controlador. Com o núcleo pronto, saem rápido.

### Fase 5 — Registro Auxiliar do RI

Fecha a lacuna do Livro 3.

### Fase 6 — o selador

Depois de as atribuições existirem e de a interface estar apurada em fonte primária. Nesta
ordem porque **selar é o último passo de cada ato**: sem os atos, não há o que selar; e com os
atos, cada um já sabe qual é o seu código e a sua tabela.

Passo intermediário que dá para fazer a qualquer momento, e resolve dor imediata do balcão:
**colar a imagem e o QR do selo por Ctrl+V ou arrastando** — hoje nenhum ato de 18/08 tem o QR
gravado.

### Fase 7 — a revisão manual, ato por ato

A etapa que você já planejou. Só faz sentido no fim, e é ela que transforma "funciona" em
"funciona direito".

---

## 9. Como eu quero trabalhar daqui para frente

Do jeito que a 3.3.9 foi feita, porque funcionou:

1. **Ler a fonte antes de escrever** — o acervo, a inspeção, a norma.
2. **Módulo de domínio primeiro, tela depois.** A regra em Python testável; a rota só amarra.
3. **Teste que reproduz o fato real**, não o caminho felizinho. Os 65 testes novos da 3.3.9
   nasceram todos de algo que aconteceu no dia 18.
4. **Ensaio contra cópia do banco de produção** antes de qualquer entrega.
5. **Nada entra em atendimento sem a seção "como cancelar ou desfazer" escrita no manual.**

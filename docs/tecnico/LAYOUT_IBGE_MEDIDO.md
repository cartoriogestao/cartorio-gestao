# A remessa do IBGE — medida, e depois confirmada pela especificação

> **Este documento foi reescrito em 28/08/2026.** A primeira versão dizia que o
> arquivo **não se gera**, porque seis posições não se explicavam. O oficial
> indicou um caminho, e por ele se chegou à **especificação oficial do IBGE** —
> que fechou as seis. O que segue é a versão fechada; a história de como ela
> fechou fica, porque a lição está nela.

---

## De onde saiu

**Novas instruções para a geração dos arquivos dos cartórios informatizados para
o sistema Registro Civil do IBGE** — Diretoria de Informática, COPRE/GESIP,
atualizada em 08/01/2015. Trinta páginas.

E ela foi **conferida contra os arquivos que esta casa exportou**, em
`C:\ARPNET\C11\IBGE_EXP`.

---

## Como se chegou nela, e por que isso importa

Primeiro os arquivos foram **medidos**, cruzando 28 linhas de nascimento com 28
assentos do acervo. Saíram oito campos, todos certos:

| medido | a especificação confirma |
|---|---|
| dia e mês do registro | `DATAREGDIA`, `DATAREGMES` |
| data de nascimento, `ddmmaaaa` | `DATA-NASC` |
| **sexo** — 1 masculino, 2 feminino | `SEXO`, e a tabela tem o `9 = ignorado` que a amostra não mostrou |
| UF e município de nascimento | `COD-UF-NASC`, `COD-MUNIC-NASC` |
| município de residência da mãe | `COD-MUNIC-RES-MAE` |
| o número da DN | `DN` |

E sobravam seis posições que a medição não alcançava. Elas eram:

| posição | o que era |
|---|---|
| 45 | **local do nascimento** — 1 hospital, 2 sem internação, 3 domicílio, 5 outros, 9 ignorado |
| 53 | **gêmeo** — 1 não, 2 gêmeo, 3 trigêmeo ou mais, 9 ignorado |
| 57–59, 62–64, 72–74 | **país** de nascimento do pai, da mãe e de residência — `076` é o Brasil |
| 75–76 | **idade da genitora** — 10 a 69, e `99` quando ignorada |

> **A lição está no meio do caminho.** Eu havia testado a posição 75-76 contra a
> idade da mãe e concluído que **não era** — porque num dos casos o arquivo diz
> `01` e a mãe tinha quarenta e quatro anos. Era a idade sim: o que estava
> errado era o **dado do acervo**, não a minha leitura da posição.
>
> **Amostra pequena com dado sujo desmente hipótese certa.** Vinte e oito linhas
> bastaram para achar oito campos e não bastaram para os outros seis — e a
> conclusão «não é isso» custou mais que a conclusão «não sei».

---

## O layout, fechado

Os cinco arquivos vão zipados em `CARTINF.ZIP`:

| arquivo | modelo | largura | conferido |
|---|---|---|---|
| `CARTINF01.TXT` | nascidos vivos | **112** | 28 linhas reais |
| `CARTINF02.TXT` | casamentos | **105** | 2 linhas reais |
| `CARTINF03.TXT` | óbitos | **103** | 13 linhas reais |
| `CARTINF04.TXT` | óbitos fetais | 102 | vazio nesta casa |
| `CARTINF10.TXT` | resumo, folha RC-10 | **68** | 4 linhas reais |
| `CONTROLE.SIS` | controle do IBGE | — | vazio |

**A chave de identificação** é UF + município + distrito + código do cartório, e
ela abre toda linha de todo arquivo. Nesta casa: `21` `07001` `05` `01`.

Em **ISO-8859-1**, com `CRLF`. Acento em dois bytes empurraria todos os campos
da linha para a direita — a mesma lição do retorno da CRA.

**`CHAR` alinha à esquerda com espaço; `NUM` alinha à direita com zero** — com
uma exceção medida: nos três modelos de registro o `NUM-REGLIV` vem alinhado à
**esquerda** (`'19506  '`), e no RC-10 vem com zeros (`'0019506'`). Os dois
foram aceitos pelo IBGE, e o que vale é o arquivo.

---

## A prova é o ida e volta

Ler cada arquivo real e reescrevê-lo tem de sair **byte a byte igual**. É a
mesma prova do leitor da CRA, e ela pega o que nenhuma outra conferência pega:
campo fora de lugar, alinhamento trocado, largura errada.

Os quatro passam.

> **E ela produziu um achado sobre o arquivo, não sobre o layout:** duas das
> treze linhas de óbito que esta casa mandou têm **102 posições em vez de 103** —
> falta exatamente um espaço no fim. As outras onze estão certas. Algum programa
> aparou o espaço final ao gravar; o IBGE aceitou, e o que se escrever daqui em
> diante sai completo.

---

## O que faltava, e o que foi fechado em 28/08/2026

A primeira versão deste documento terminava dizendo que faltava **o dado**, e
que ele era da casa. Faltavam quatro coisas. As quatro fecharam.

### 1. O código do município — o impasse que travava tudo

O layout pede **código** (`21`, `07001`); o sistema guarda **nome** («Cidade Exemplo»). Sem de-para, cada município teria de ser digitado em código pelo
escrevente, e código digitado à mão numa remessa estatística é o pior tipo de
erro: ninguém lê o arquivo depois para conferir.

O acervo tinha a resposta em duas tabelas que ninguém abrira:

| tabela | linhas | códigos distintos |
|---|---|---|
| **`tbMunicipio`** | 5.638 | **5.570** — o número de municípios do Brasil |
| `MUNICIPIOS` | 5.444 | 5.444 (faltam 126) |

Ficou a primeira, em `ib_municipios`. As 68 linhas sem código são restos de
município renomeado ou desmembrado, e entram como **rejeição escrita**, não como
silêncio.

### 2. O cabeçalho — quem esta serventia é, na fala do IBGE

`tbIBGE_Propriedades` guardava o que a casa mandava: UF `21`, município `07001`,
distrito `05`, cartório `01`. Virou configuração (`settings`), como o CNS.

> **As duas fontes se conferem sozinhas**, e foi isso que permitiu usá-las sem
> acreditar em nenhuma isoladamente: o código IBGE de Cidade Exemplo é `2198765`,
> que é exatamente `21` + `07001` do cabeçalho.

### 3. Local do nascimento, gêmeo, DNV e DO — e o de-para que quase passou batido

Os três primeiros não existiam em `rc_assentos`, e o quarto (o número da
Declaração de Óbito) também não. Agora existem, com **caixa de seleção** para os
dois que têm catálogo — código de IBGE digitado à mão é erro que ninguém confere.

**E aqui houve um susto.** O acervo guarda `intCodigoLocalNascimento` com valores
1, 2, 3 e **4** — e o catálogo do IBGE **não tem 4**: ele pula do 3 para o 5.
Mandar o código do E-Ofício direto faria o IBGE recusar.

O de-para estava no próprio acervo, com esse nome: **`tbRCPN_LocalNascimento` tem
a coluna `intCodigoIBGE`**, e ela diz que o `4` de lá («Outros») é o `5` do IBGE,
e o `5` («Ignorado») é o `9`.

> **Antes de deduzir um de-para, procure a coluna que já o tem.** Ela estava a um
> `PRAGMA table_info` de distância.

### 4. Os catálogos do óbito — fechados por dois caminhos

`NATUREZA` e `LOCAL` do óbito não estavam medidos. Foram fechados assim:

**Primeiro medidos**, nas 13 linhas de óbito que esta casa exportou, cruzadas com
os 31 óbitos do acervo pelo número do registro:

| o acervo diz | o arquivo traz | vezes |
|---|---|---|
| Hospital | `LOCAL 1` | 7 |
| Via Pública | `LOCAL 4` | 1 |
| Outros | `LOCAL 5` | 5 |

**Depois confirmados** pela especificação oficial, que traz as listas inteiras —
inclusive `3 = domicílio`, que a amostra desta casa não mostrou:

- **NATUREZA**: 1 natural, 2 violenta, 9 ignorado
- **LOCAL**: 1 hospital, 2 outros estabelecimentos de saúde sem internação,
  3 domicílio, 4 via pública, 5 outros, 9 ignorado
- **TIPO-TEMPO**: 0 minutos, 1 horas, 2 dias, 3 meses, 4 anos, 9 ignorado
- **EST-CIV**: 1 solteiro, 2 casado, 3 viúvo, 4 separado judicialmente,
  6 divorciado, 7 desquitado, 9 ignorado

> **A coincidência que fecha a natureza**: a única linha com `NATUREZA 2` é
> justamente a morte em **via pública** de um homem de 26 anos. «Violenta»
> encaixa; nenhuma outra leitura encaixaria as duas coisas ao mesmo tempo.

**O catálogo do óbito não é o do nascimento**, e a diferença é o `4`: o óbito tem
«via pública» e o nascimento não. Usar um pelo outro mandaria «outros» onde o
IBGE espera «via pública» — que é a informação que ele mais quer, porque é onde a
morte violenta acontece.

**E catálogo oficial pula número**: o local do nascimento não tem 4; o estado
civil do falecido não tem 5. Quem preencher a sequência «óbvia» acerta o tipo do
campo e erra o conteúdo, e o IBGE recusa o trimestre inteiro meses depois, sem
dizer qual linha.

---

## O que ainda falta

A **montagem do arquivo** a partir dos atos lavrados — juntar o assento, as
pessoas, os municípios e os catálogos numa linha de 112 posições. O layout está
fechado, os códigos estão fechados e o dado passou a existir; o que falta é a
função que costura os três, e a tela que a chama.

Para os assentos **antigos**, a remessa sai do acervo, que é onde os dados estão.
Para os **novos**, sai do que a casa lavrar — e é isso que os campos criados hoje
tornaram possível.

# O selador do TJMA, aprendido por 26.130 usos

Não encontrei manual. Encontrei coisa melhor: **o registro de todas as 26.130 vezes que esta
serventia selou um ato entre 19/03/2020 e 17/08/2026**, com o que foi enviado, o que voltou e
o que saiu impresso. Está em `tbSeloIndividual`, e é dela que sai tudo abaixo.

> **Correção de 24/08, e a lição vale para o resto do projeto.** Eu havia concluído, do fato de
> `tbServico.strURL_Selador` só trazer caminhos de RTD/RCPJ, que o E-Ofício selava automático
> apenas nessas duas atribuições. **Está errado** — o oficial, que operou o sistema, corrigiu:
> selava em todas.
>
> A prova está nesta mesma tabela, e é forte: as 26.130 linhas têm `memJson` — o payload
> enviado ao selador — preenchido em **todas** as atribuições, e `strURLAto` guarda o caminho
> de cada selo. São **26.123 selos em 34 caminhos**:
>
> | Atribuição | Caminhos | Selos | O mais usado |
> |---|---|---|---|
> | Notas | 9 | 21.129 | `/selo/notas/reconhecimento-firma` (13.776) |
> | RI | 6 | 2.108 | `/selo/imovel/prenotacao` (829) |
> | RCPN | 7 | 1.413 | `/selo/civil/atos-em-geral` (1.238) |
> | Protesto | 6 | 1.308 | `/selo/protesto/pagamento` (465) |
> | RTD/RCPJ | 6 | 165 | `/selo/rtdpj/atos-em-geral` (53) |
>
> Está em `atribuicoes.CAMINHOS_USADOS_POR_ESTA_CASA`, com o número de selos por caminho — que
> serve para escolher o que implementar primeiro.
>
> **Um caminho usado não está no contrato**: `/selo/rtdpj/atos-em-geral-com-livro`, 46 selos,
> ausente da documentação de 2017. O `memJson` diz a forma dele — `ato`, `partes` e `selo` com
> escrevente, folha, livro e termo; é a variante "com livro" do `atos-em-geral`. Não entrou em
> `selador.ENDPOINTS` de propósito: aquela tabela vem da documentação oficial, e misturar
> medição com documentação apagaria a procedência das duas.
>
> **A lição:** coluna vazia não prova que a coisa não acontecia — prova que aquela coluna não
> era onde ela ficava.

> **Atualização de 21/08.** Depois de escrever isto, com o acesso a `C:\ARPNET` aprovado, **o
> manual apareceu** — a documentação oficial da API, de 2017, estava na sua própria máquina, na
> pasta do Selo Eletrônico. Os capítulos 1 a 6 abaixo continuam valendo: foram escritos por
> dedução e a documentação os confirmou. O **capítulo 7 foi reescrito** com o que ela trouxe.

> **Antes de tudo, uma correção do que eu te disse ontem.** Eu havia concluído, olhando
> `tbServico.strURL_Selador`, que nesta serventia **só RTD e RCPJ** selavam automaticamente.
> **Está errado.** A coluna `strURLAto` de `tbSeloIndividual` mostra que Notas, Registro Civil
> e Registro de Imóveis também selavam pelo selador — **22.913 atos**. A coluna de serviço só
> tinha sido preenchida para RTD/PJ; nos outros o caminho estava dentro do programa.
>
> Conclusão que muda o projeto: **o selo automático não é território novo. É o normal desta
> casa desde 2020, e o que fizemos em 18/08 — colar selo à mão — é que era a exceção.**

---

## 1. Como funciona: o selo vem na hora, e não de um talão

Isto estava em dúvida no levantamento de ontem, e os dados resolvem:

| Campo | Estado nos 26.130 selos |
|---|---|
| `bitReservado` | **falso em todos** |
| `bitPendenteEnvioTJ` | **falso em todos** |
| `bitLiberadoParaEnvioTJ` | **falso em todos** |
| `bitEnviadoTJ` | **falso em todos** |
| `memJson` (o que foi enviado) | **preenchido em 26.123** |
| `strURLAto` (o endereço chamado) | **preenchido em 26.123** |

A fila de "enviar ao Tribunal" **nunca foi usada** — é resquício de um desenho anterior. E
praticamente todo selo tem o pedido guardado.

**O selo é pedido ao selador no momento do ato, e a resposta volta com o código, o valor e o
texto pronto.** Não há faixa de selos consumida localmente.

## 2. Os endereços — o mapa real, tirado de 26 mil chamadas

O caminho é `/selo/{atribuição}/{ato}`:

| Endereço | Chamadas |
|---|---|
| `/selo/notas/reconhecimento-firma` | 13.776 |
| `/selo/notas/autenticacao` | 3.664 |
| `/selo/notas/cartao-assinatura` | 2.667 |
| `/selo/civil/atos-em-geral` | 1.238 |
| `/selo/imovel/prenotacao` | 829 |
| `/selo/notas/atos-em-geral` | 739 |

E, do cadastro de serviços, mais doze de RTD/RCPJ: `ato-declarado/integral/com-valor`,
`ato-declarado/integral/sem-valor`, `ato-declarado/resumido/sem-valor`, `atos-em-geral`,
`busca-ate-dez-anos`, `acima-tres-diligencias`, `apostila-haia`, `diligencia/zona-urbana`,
`matricula`, `pessoa-juridica/averbacao`, `pessoa-juridica/certidao`,
`titulo-documento/certidao/por-peca`.

**Quatro espaços de nome:** `notas`, `civil`, `imovel`, `rtdpj`. Não há `protesto` entre os
observados — os selos de protesto existem (PROTIT, LIQTIT, DILIGE, ARQUIV), mas o caminho
usado não ficou gravado. **Lacuna a confirmar.**

A base — URL, usuário e senha — morava em `tbSeladorConfiguracao`, três colunas, e saiu
**vazia** na exportação. É o único pedaço que ainda falta, e é o que está na máquina.

## 3. O que se envia: um formato por tipo de ato

Não é um formato só, e não é versionado. **Cada tipo de ato tem o seu.** Estes são reais,
dos últimos atos de agosto de 2026, com nome e documento mascarados:

**Autenticação** — `/selo/notas/autenticacao`

```json
{"escrevente": "ESCREVENTE", "quantidade": 1,
 "ato": {"codigo": "13.18", "codigoTabelaCusta": "0520260101"}}
```

**Reconhecimento de firma** — `/selo/notas/reconhecimento-firma`

```json
{"escrevente": "ESCREVENTE", "natureza": {"tipo": 1},
 "nomesReconhecido": {"nomePartes": "…", "parteAto": [{"nome": "…", "documento": "…"}]},
 "ato": {"codigo": "13.17.4", "codigoTabelaCusta": "0520260101"}}
```

**Registro de óbito** — note o **papel de segurança** indo no pedido

```json
{"codigoTipoAtoRegistro": "14.c",
 "dadosSelo": {"escrevente": "ESCREVENTE", "livro": "5", "folha": "275",
               "termo": "1976", "isentoGratuito": "ISENTO",
               "motivoIsentoGratuito": "REGISTRO DE ÓBITO",
               "versaoTabelaDeCustas": "0120260101"},
 "parte": {"nome": "…"}, "nomeParte": "…",
 "papelMoeda": {"codigo": "7225296", "fornecedor": "ARPENBRASIL", "utilizado": false}}
```

**Prenotação do Registro de Imóveis** — `/selo/imovel/prenotacao`

```json
{"dadosSelo": {"codigoTipoAto": "16.1", "livro": "1A", "escrevente": "ESCREVENTE",
               "naturezaTitulo": 126.0, "descricaoNatureza": "CEDULA DE CREDITO BANCARIO",
               "isento": false, "descontoProvimento279": false,
               "partes": {"nomePartes": "…", "parteAto": [{"nome": "…", "documento": "…"}]}}}
```

### O vocabulário do pedido, reunido

`escrevente` · `quantidade` · `ato.codigo` · `ato.codigoTabelaCusta` · `natureza.tipo` ·
`natureza.descricao` · `nomesReconhecido.parteAto[]` · `partes.parteAto[]` · `livro` ·
`folha` · `termo` · `protocolo` · `matricula` · `registroAverbacao` · `valorTitulo` ·
`baseCalculo` · `valorDeclarado.valorDeclarado` · `valorDeclarado.valorAvaliado` · `isento` ·
`isento.motivo` · `isentoGratuito` · `motivoIsentoGratuito` · `reterIss` ·
`percentualDesconto` · **`descontoProvimento279`** · `naturezaTitulo` · `papelMoeda.codigo` ·
`papelMoeda.fornecedor` · `papelMoeda.utilizado` · `convenio.convenio` ·
`convenio.dataApresentacaoTitulo` · `versaoTabelaDeCustas` · `codigoTipoAto` ·
`codigoTipoAtoRegistro` · `codigoTipoAtoCertidao`.

> **Dois achados que a inspeção vai cobrar, e que já estão no pedido.** `isentoGratuito` com
> `motivoIsentoGratuito` é a **gratuidade** — e a inspeção manda "padronizar imediatamente
> emolumentos, destinações, **gratuidade** e selo nos nascimentos". E `papelMoeda` no corpo do
> pedido significa que **o papel de segurança é declarado ao Tribunal na hora de selar**: o
> estoque de papel não é controle interno, é parte do ato.

> **`descontoProvimento279`** é referência a um provimento que eu ainda não li. Entra na lista
> de perguntas à COGEX.

## 4. A tabela de custas: dois dígitos e uma data

`codigoTabelaCusta` e `versaoTabelaDeCustas` têm o formato `TTAAAAMMDD`:

`0520260101` = tabela **05**, vigência **01/01/2026**.

Tabelas observadas: **01, 02, 03, 05** — e batem com a atribuição do ato (05 nos atos de
Notas, 01 no registro de óbito). Vigências observadas: 12/10/2020, 28/03/2021, 12/10/2021, e
1º de janeiro de 2022, 2023, 2024, 2025 e 2026.

**72 códigos de ato distintos** foram usados, na estrutura da tabela do TJMA — 13.x nas Notas,
14.x no Registro Civil, 16.x no Registro de Imóveis, 17.x no Protesto. Os mais usados:

| Código | Chamadas | | Código | Chamadas |
|---|---|---|---|---|
| 13.17.2 | 7.463 | | 16.1 | 799 |
| 13.17.4 | 4.973 | | 13.30 | 737 |
| 13.18 | 3.666 | | 16.24.4 | 385 |
| 13.17.1 | 2.708 | | 16.24.4.1 | 333 |
| 13.17.3 | 1.342 | | 17.2 | 269 |
| 14.5.1 | 1.038 | | 17.9 · 17.10.1 | 263 cada |

## 5. O que volta: o texto pronto, e é isso que muda o balcão

```
Poder Judiciário – TJMA. Selo: PRENOT000000ZEZSIN46Y2QXQM16, 17/08/2026 08:50:12,
Ato: 16.1, Parte(s): PESSOA EXEMPLO, Total R$ 43,37 Emol R$ 38,72
FERC R$ 1,16 FADEP R$ 1,55 FEMP R$ 1,55 FERRFIS R$ 0,39
Consulte em https://selo.tjma.jus.br
```

**É exatamente o texto que a substituta colou à mão em 18/08.** O selador já devolve pronto —
com o código, a data, o ato, as partes, o total e a repartição por fundo. O sistema não precisa
compor nada disso: precisa **guardar**.

E vem também o **valor total** (`curValorTotal` preenchido em 25.489 selos), o **valor do QR**
(`strvalorQRCode`, em 25.642) e o endereço chamado.

### O formato do código

`PRENOT000000ZEZSIN46Y2QXQM16` — **28 caracteres**: seis letras do tipo de ato, o **CNS 000000**
da serventia, e dezesseis de identificação. Há 488 selos antigos em outro formato, 32 dígitos
hexadecimais.

Os **39 prefixos** observados, e o que cada um sela: RECFIR (firma, 16.355) · AUTENT
(autenticação, 3.652) · CERTID (certidão, 1.237) · ARQUIV (arquivamento, 939) · PRENOT
(prenotação, 816) · CERINT (inteiro teor, 590) · PROTIT (protesto de título, 390) · CERELE
(certidão eletrônica, 368) · CERIMV (certidão de imóvel, 335) · DILIGE (diligência, 264) ·
LIQTIT (liquidação, 190) · PROCUR (procuração, 176) · AVESVD (averbação sem valor declarado,
51) · BUSCAS (51) · MATRIC (35) · ESCPUB (escritura pública, 34) · REGNAS (nascimento, 13) ·
REGOBT (óbito, 8) — e mais vinte de uso raro.

## 6. Duas coisas que os dados denunciam, e que ninguém pediu para eu procurar

**1.304 selos foram obtidos e nunca usados** — 5% de tudo. Quinhentos só em 2025. Desses,
**522 não têm nem protocolo geral**, e **apenas 5 foram cancelados**. São selos que a serventia
pediu ao Tribunal, não gastou e não cancelou.

> Não sei o efeito fiscal disso, e não vou afirmar o que não sei. Mas é uma pergunta que a
> correição pode fazer, e é melhor a serventia ter a resposta antes. O sistema novo precisa de
> uma tela de **selo obtido e não usado**, para que isto não se acumule em silêncio.

**79 selos foram cancelados, e 74 deles já tinham sido usados.** Ou seja: cancelar selo de ato
já praticado é procedimento conhecido nesta casa — é o que você está fazendo com o AV-03. Não é
excepcional. E **nenhum dos 79 tem motivo gravado** (`intCodigoMotivo` nulo em todos). O sistema
novo grava o motivo: a ata de ocorrência do expurgo já faz isso.

## 7. Depois disto: a documentação oficial apareceu, na sua própria máquina

Este capítulo foi escrito por dedução, a partir dos 26.130 usos. **Já não é mais preciso deduzir.**
Com o acesso a `C:\ARPNET` aprovado, encontrei a **documentação oficial da API do selador**, do
Tribunal, em:

```
C:\ARPNET\C11\Selo Eletrônico\selador-doc\{notas,protesto,civil,imovel,rtdpj,maritimo}\index.html
```

Datada de **08/10/2017**. De lá saíram **181 endpoints** — cada um com o nome do campo que
envolve o corpo do pedido e o nome do seu schema — e **115 schemas**, campo por campo, marcados
como obrigatório ou opcional. E de dentro do `e-oficio-ma.exe` saíram os dois endereços:

| | |
|---|---|
| Produção | `https://selador.ma.portalselo.com.br:9443` |
| Autenticação | `https://ma.portalselo.com.br:9443/auth` (Keycloak, `client_id=selador`, senha do usuário) |

Confrontei os **26.123 pedidos reais** do acervo contra os schemas oficiais:

```
bateram exatamente:                22.523  (86,2%)
obrigatório não enviado:           nenhum
endpoint fora da documentação:         46  (/selo/rtdpj/atos-em-geral-com-livro)
campo fora do schema:               3.572  (quantidade, isento, convenio)
```

Nenhum campo obrigatório faltando em 26 mil chamadas é o melhor sinal possível: o contrato de
2017 continua valendo. As cinco diferenças são **acréscimos posteriores** à documentação, e estão
registradas no código em `selador.ALEM_DA_DOCUMENTACAO` para que ninguém as tome por erro.

### Correção importante: esta serventia não sela pela internet

Eu havia concluído que o sistema deveria chamar direto o endereço do Tribunal. A tabela
`tbSeladorConfiguracao` do acervo diz outra coisa — e ela tem exatamente três colunas:

| Coluna | Valor |
|---|---|
| `strUrlSelador` | **`https://192.0.2.23:443`** |
| `strUsername` | preenchido, 16 caracteres — não extraído |
| `strPassword` | preenchido, 8 caracteres — não extraído |

**`192.0.2.23` é um endereço de rede local.** Esta casa não fala com o TJMA pela
internet: fala com um **Selador instalado numa máquina do escritório**, que é quem
guarda o estoque de selo e conversa com o Tribunal. Os endereços que eu tinha extraído
do `e-oficio-ma.exe` são o padrão de fábrica compilado no programa; o que vale é o
configurado.

Isso mudou a arquitetura do módulo: **nada em `selador.py` assume a base**. Quem chama
informa o endereço, e o padrão de fábrica só entra se ninguém disser o contrário.
Apontar para a nuvem uma casa que sela num appliance local dá 401 no meio do
atendimento — ou, pior, sela em duplicidade.

### O que ainda falta — agora são duas coisas, e as duas são suas

| Falta | Onde você vê |
|---|---|
| **Usuário e senha** do selador | no E-Ofício, tela **Selador — Propriedades** (campos *Username* e *Password*) — elas existem e estão gravadas, mas eu não as li |
| **URL de homologação** | mesma tela, campo *URL de Homologação*. Não está em `tbSeladorConfiguracao`, que só tem as três colunas acima |

Não extraí a senha de lugar nenhum, de propósito, e não a guardei em nenhum arquivo — no
sistema novo ela entra pela tela de configuração da serventia, como qualquer outra
senha, e fica no banco da casa. E deixei `BASE_HOMOLOGACAO = None` no código em vez de
adivinhar: chutar endereço de homologação e pedir para selar achando que era teste é o
tipo de erro que gera selo verdadeiro e cobrado.

### De quebra: as 4.337 imagens de QR já existem

Em `C:\ARPNET\C11\SeloDigital` há **4.337 arquivos `.png` nomeados exatamente pelo
código de 28 caracteres do selo** — `ARQUIV000000012EG1CZM98CVV41.png` e assim por
diante. É a imagem do QR que sai impressa.

Isso responde a dois itens da lista da J. de 18/08: *"a imagem do QR do selo"* e
*"colar o selo por Ctrl+V ou arrastar"*. Não precisamos gerar nada para o acervo — a
imagem de cada selo já praticado está em disco, achável pelo código. Para os selos
novos, o QR vem do próprio selador.

Duas dúvidas do quadro antigo ficaram **respondidas**, e não pelo Tribunal:

- **O caminho do protesto** existe e está documentado — são 24 endpoints em `/selo/protesto/…`.
  A lacuna era do nosso acervo, não da API.
- **O Provimento 279** é da **Corregedoria-Geral de Justiça do Amazonas**, não do Maranhão. O
  campo `descontoProvimento279` aparece nos schemas porque o selador é um produto de prateleira
  usado por vários estados. Aqui, marcá-lo seria conceder desconto sem base legal — o código
  **recusa** enviá-lo com valor verdadeiro. Vale confirmar com a COGEX, mas a leitura é essa.

### Uma terceira coisa que os dados denunciaram, e que a documentação explicou

A API aceita um parâmetro **`SID`** — um identificador que você escolhe e que o Tribunal usa para
não gerar dois selos para o mesmo pedido. **1.304 selos do acervo (5%) nunca foram usados, e só 5
deles foram cancelados.** É exatamente a marca de quem repetiu a chamada depois de um erro de
rede sem mandar um SID: cada tentativa gerou selo novo, cobrado, e o anterior ficou órfão.

No sistema novo o `SID` é calculado por SHA-256 a partir do CNS, da atribuição e da referência do
ato — **nunca da hora** —, de modo que repetir a chamada devolve o selo que já existe em vez de
comprar outro.

## 8. Como isto muda o plano

O selador saiu de "peça mais arriscada, deixar para o fim" para **"contrato conhecido, com
documentação oficial e 26 mil exemplos"**. O que falta é credencial, não desenho.

Propus **antecipar** o módulo de selo para dentro da Fase 1, junto do núcleo, e **já o fiz**,
porque:

- ele é **igual para as seis atribuições** — mesmo endereço-base, mesma autenticação, mesmo
  formato de resposta, mesma tabela de custas;
- cada atribuição nova já nasce selando, em vez de nascer colando à mão e ter de ser
  retrabalhada;
- e o pedaço que depende de credencial — a chamada de rede — é o **último** da cadeia: o
  registro do selo, o texto, o QR, o valor, a vinculação ao livro e folha, a tela de selo não
  usado e o cancelamento, tudo isso se constrói e se testa **sem tocar no Tribunal**, com os
  26.130 exemplos reais servindo de caso de teste.

### O que já está construído, na versão 3.4.3

| Módulo | O que faz | Testes |
|---|---|---|
| `atribuicoes.py` | as 6 atribuições, 72 atos, 11 tipos de selo, 12 tipos de papel, os 5 fundos e seus sinônimos | 54 |
| `selo.py` | lê e confere o código de 28 caracteres (39 prefixos), lê o texto impresso do selo, lê a tabela de custas | 157 |
| `livro_nucleo.py` | a geometria dos 24 livros das 6 atribuições — folhas, verso, páginas pares, transbordo | incluso |
| `selador.py` | os 181 endpoints, os 115 schemas, a autenticação, o `SID` determinístico, a leitura da resposta e do erro | 172 |
| `escrituracao.py` | abrir livro, achar lugar, lançar, inutilizar, encerrar livro, encerrar o dia | 41 |
| `custas.py` | emolumento, os quatro fundos, gratuidade e vigência **por data do ato** | 29 |
| `protesto_cra.py` | o contrato da CRA/CENPROT: 64 espécies, 76 irregularidades, 11 ocorrências | 24 |

No sistema inteiro: **985 testes passando**, 4 ignorados. Nada disso chama o Tribunal —
a chamada de rede é a próxima peça, e depende só das duas credenciais do quadro acima,
mais o endereço do Selador da rede local.

# AS APIs DAS SEIS ATRIBUIÇÕES — o mapa medido, para planejar

Escrito em **03/09/2026**, por ordem do oficial:

> «vamos inserir todas api de todas atribuições que temos»
> «documente tudo agora, entramos numa fase de planejamento»

**Este documento não constrói nada.** Ele mede, e diz o tamanho de cada peça —
para que a decisão do que fazer primeiro seja dele, com os fatos na mão.

**Tudo o que segue foi baixado dos endereços públicos e conferido**, como o WSDL
da CRA e o swagger da CENPROT. Onde não deu para medir, está escrito que não deu.

---

## 1. O QUADRO — onde cada atribuição está hoje

| # | atribuição | Central | contrato | estado |
|---|---|---|---|---|
| 1 | **Notas** | CCN / e-Notariado | OpenAPI 3.0.1 · 11 caminhos | **medido**, não construído |
| 2 | **Protesto** | CRA-MA (IEPTB) | WSDL · 21 operações | **construído** — `cra21_api.py` |
| 2 | **Protesto** | CENPROT Nacional | Swagger 2.1.0 · 20 caminhos | **construído** — `cenprot_api.py` |
| 3 e 4 | **RCPJ e RTD** | ONRTDPJ | Swagger 2.0 · 81 caminhos | **construído** — `onrtdpj_api.py` |
| 5 | **Registro de Imóveis** | ONR / SREI | OpenAPI 3.0.3 · **39 caminhos** | **medido**, não construído |
| 6 | **Registro Civil** | ON-RCPN — e-Proclamas | Swagger 2.0 · 3 caminhos | **construído** — `onrcpn_api.py` |
| 6 | **Registro Civil** | ON-RCPN — Certidão | OpenAPI 3.0.0 · 10 caminhos | **medido**, não construído |
| — | (todas) | Selador FPFTech | 181 endpoints | **construído** — `selador.py` |

**QUATRO CONSTRUÍDAS, TRÊS MEDIDAS E POR CONSTRUIR** — a linha do
e-Proclamas mudou em **03/09/2026**, quando o oficial mandou seguir o
cronograma («temos tempo») e o primeiro item saiu. Ver
`O_EPROCLAMAS_CONSTRUIDO.md`.

Os contratos dos que faltam estão guardados em `FONTES_EXTERNAS/`, que **não
viaja no `.cgu`**.

> **E o e-Proclamas cobrou uma correção grande deste próprio documento.** Está
> escrito abaixo, na seção 3, que a resposta dele não foi medida — **foi, e
> errado**: eu imprimi só a `description` de cada resposta, li «OK», e conclui
> que o corpo não era declarado. Ele é, e traz **duas listas por matrícula**
> (`success` e `error`): HTTP 200 **não** quer dizer que o proclama subiu.
> Quem for construir as outras três leia isso antes — a armadilha é do mesmo
> feitio nas quatro.

---

## 2. REGISTRO DE IMÓVEIS — ONR · a maior das quatro

| | |
|---|---|
| documentação | `https://www.registrodeimoveis.org.br/swagger/index.html` |
| contrato | `https://www.registrodeimoveis.org.br/swagger/openapi.json` |
| guardado em | `FONTES_EXTERNAS/onr_ri/openapi.json` — 412.878 bytes |
| versão | **OpenAPI 3.0.3** · «API - Registro de Imóveis do Brasil 1.0.0» |
| caminhos | **39** · **73 esquemas** |

**E ELA DECLARA OS DOIS AMBIENTES**, ao contrário da ONRTDPJ:

```
https://api.registrodeimoveis.org.br            produção
https://testes-api.registrodeimoveis.org.br     testes
```

**Autenticação:** `POST /v1/auth/token` (corpo `x-www-form-urlencoded`) devolve
o token, que vai em `Authorization: Bearer`. O contrato declara **três** esquemas
— `oauth2` (clientCredentials), `bearerAuth` (JWT) e `headerAuth` (apiKey no
cabeçalho `token`) —, e a prosa da documentação diz *«O token de autenticação
deve ser sempre informado no cabeçalho "Authorization / Bearer"»*.

> **A CONFERIR: o `tokenUrl` do fluxo `oauth2` está escrito `https://teste/oauth2/token`** —
> um endereço que não existe. É sobra de configuração, e quem seguisse aquele
> campo não chegaria a lugar nenhum. Vale a prosa e o `/v1/auth/token`.

### As sete famílias

| família | caminhos | o que faz |
|---|---|---|
| **Autenticação** | 2 | gerar e validar o token |
| **Indicador** | 9 | **o indicador real** — enviar, listar, atualizar, excluir, e os atos de cada um |
| **Cobrança** | 8 | cadastrar, gerar, listar, cancelar, **devolução PIX**, tipos de pagamento |
| **Protocolo** | 12 | **enviar protocolo online**, em lote, detalhes, token de acesso (v1 e v2), download de anexo |
| **Edital** | 17 | gerar, retificar, cancelar, **edital de leilão**, e a extração de dados |
| **Fila de Processamento** | 2 | acompanhar o que foi mandado em lote |
| **Atendimento Eletrônico** | 3 | a fila do atendimento, os detalhes e as interações |

### O que isso substitui nesta casa

**`ri_onr.py` gera o indicador real como ARQUIVO e não manda nada.** O
cabeçalho dele diz, com todas as letras: *«Nada aqui transmite arquivo. A
geração produz o arquivo para conferência e envio manual pelos canais do
ONR.»* E `tbONR_Propriedades` do E-Ofício guarda duas pastas
(`\\Servidor\c11\ONR\xmls` e `E:\C11\ONR\INDICADOREAL`) — arquivo em disco,
enviado à mão.

**`POST /v1/indicador/real` é o envio.** O trabalho de montar o dado já está
feito; o que falta é o transporte.

**E o `Atendimento Eletrônico` é o SAEC** — o Serviço de Atendimento Eletrônico
Compartilhado, por onde chega o pedido de certidão e de pesquisa do RI. É o
equivalente, no RI, do que a fila da ONRTDPJ é no RTD.

### E há um defeito medido no contrato deles

**O `openapi.json` do ONR NÃO É JSON VÁLIDO.** Medido: **duas vírgulas antes de
fecho** (`,}`), uma delas na linha 12100, em `urlNotaFiscal`. Qualquer parser
padrão recusa o arquivo inteiro — o Python recusou.

Depois de tirar as duas, ele lê: **39 caminhos, 73 esquemas**. A cópia limpa
está ao lado, em `openapi_limpo.json`, e **a original fica**: é ela que prova o
defeito, e no dia em que corrigirem o teste avisa.

> É a família do `http://` no WSDL da CRA e do `application/form-data` da
> ONRTDPJ, pela terceira vez: **contrato publicado tem erro, e quem o consome
> tem de decidir o que fazer com ele — à vista.**

**Outros dois links que o oficial mandou:**
`registrodeimoveis.org.br/manual-api-editais` (o manual do edital) e
`status.onr.org.br/public-api` — esta última é a **página de status** do ONR,
com `https://status.onr.org.br/v3/summary.json` e `/components.json`, pública e
sem autenticação. Serve para a tela dizer «a Central está fora do ar» em vez de
mostrar lista vazia, que é a regra que este projeto já aplica.

### A CERTIDÃO AUTOMÁTICA DO RI — o caso de uso que o ONR já documenta

O oficial apontou a notícia do Colégio Registral do RS. **A «Certidão
Automática do RI» é a ponte que liga a plataforma eletrônica aos Registros por
uma API**: o pedido chega pelo **SAEC**, e o sistema do cartório recebe, assina,
confere se há registro e devolve o documento — com QR, marca-d'água, hash de
validação e carimbo de tempo, no padrão do ONR, válido nacionalmente.

**É o mesmo desenho da fila da ONRTDPJ que esta casa acabou de construir**, num
grau a mais: ali a resposta é o número do registro; aqui é o documento assinado.

Dois manuais foram baixados para `FONTES_EXTERNAS/onr_ri/`:

| arquivo | de onde | tamanho |
|---|---|---|
| `manual_certidao_automatica.pdf` | `onr.org.br/wp-content/uploads/2024/09/ebook-final-3_compressed.pdf` | 512 KB |
| `manual_integracao_cartorios.pdf` | `ridigital.org.br/Downloads/Manualintegracaocartorios.pdf` — «versão 3.7» | 8 MB |

> **OS DOIS FORAM BAIXADOS E NÃO FORAM LIDOS**, e isso fica dito. Resumir um
> manual de 8 MB pela notícia que fala dele seria afirmar o que não se leu — o
> erro que este projeto chama de «comentário que afirma medição sem ter
> medido». **Lê-los é passo do planejamento**, e o material já está em casa.
>
> **E há dois vídeos que o oficial mandou** (`youtube.com/watch?v=j_FlAWwYvKM`
> e `?v=5QjY8j8hmgQ`) que eu **não consigo assistir**. Se eles disserem algo que
> os contratos não dizem — em especial sobre credencial e ambientes —, é dele
> que essa informação vem.

**E há uma pergunta que a assinatura levanta, e ela é grave:** a Certidão
Automática **assina** o documento. Nesta casa a assinatura é **A3 do
delegatário**, e `assinatura_digital.py` registra, medido, que **o sistema não
pode assinar** — os dois drivers PKCS#11 desta máquina dão *segmentation fault*
no `load`, código de saída 139, e carregar o driver dentro do Flask derrubaria o
balcão inteiro. **Automatizar a certidão do RI esbarra nisso antes de esbarrar
em qualquer contrato**, e o desenho de como se assina sem carregar o driver é
decisão anterior à integração.

---

## 3. REGISTRO CIVIL — ON-RCPN · duas APIs, um token só

Medido em detalhe em **`ONRCPN_AS_APIS_MEDIDAS.md`**. Em resumo:

### e-Proclamas (Swagger 2.0, 3 caminhos)

```
GET   /api/proclama/health              — respondeu HTTP 200 «Conexão com Oracle realizada com sucesso»
POST  /api/proclama/enviar              — lote de proclamas
GET   /api/proclama/recibo/:matricula   — recibo em PDF base64
```

**`publicacao` e `livro_eletronico` são dois booleanos do MESMO envio**: uma
chamada publica no e-Proclamas e gera o **Livro D Eletrônico**.

**Isto fecha um buraco declarado no `CLAUDE.md` desde 28/08/2026** — «o envio é
integração que este sistema ainda não tem». A API existe desde **10/04/2025**.

### Certidão Eletrônica (OpenAPI 3.0.0, 10 caminhos)

Cobre **as quatro espécies que esta casa emite** — `Nascimento`, `Casamento`,
`Obito` e **`InteiroTeor`** — mais a fila de pedidos de **sete módulos**:

| código | o que chega |
|---|---|
| `CRC` | certidões pelo Provimento 149 |
| `REG` | certidões pelo site `registrocivil.org.br` |
| `JUD` | certidões por CRC-Jud / Serp-Jud |
| `EPR` | pedidos do e-Protocolo |
| **`P13`** | **registro de NASCIMENTO nas Unidades Interligadas** |
| `RSE` | certidões pelo «Registre-se» |
| **`EOB`** | **registro de ÓBITO pelo «e-Óbito»** |

**Dois desses módulos não são certidão: são REGISTRO.**

### E ela cruza com dois achados abertos do revisor registral

**O achado 2** — «causa da morte, sepultamento e testamento não têm onde ser
informados», 244 de 244 vazias. O esquema `Obito` da Central pede exatamente
`causa_morte`, `nome_medico`, `crm_medico`, `local_sepultamento_cremacao` e
`existencia_bens`.

**O achado 3** — «o civil não emite certidão de inteiro teor», 23 das 145. O
esquema `InteiroTeor` está no contrato.

**Autenticação: o token IdRC serve às duas.** OAuth 2.0 / OpenID Connect,
obtido em `/api/auth`, apresentado como `Bearer` JWT. Cadastro em
`https://home.registrocivil.org.br/solicitacao-novo-client`.

> **A CONFERIR: o endereço de PRODUÇÃO.** Os dois contratos publicados são de
> **homologação** (`servicos**h**.` e `certidao**h**.`). Tirar o «h» é palpite,
> e palpite de endereço é o pior tipo: quem o usasse acharia que testa enquanto
> fala com a Central de verdade.

---

## 4. NOTAS — CCN / e-Notariado

| | |
|---|---|
| documentação | `https://pessoas.e-notariado.org.br/swagger/index.html` |
| contrato | `https://pessoas.e-notariado.org.br/swagger/api/swagger.json` |
| versão | **OpenAPI 3.0.1** · «Pessoas **2.91.0 RTM**» |
| caminhos | **11** · **32 esquemas** |
| homologação | `https://pessoas-hml.e-notariado.org.br` |
| **produção** | `https://pessoas.e-notariado.org.br` |

**Os dois ambientes estão documentados**, ao contrário do ON-RCPN.

**Autenticação — dois cabeçalhos, e nenhum é senha:**

```
X-Api-Key:     <aplicação>|<chave de 64 caracteres>
X-Subscription: <UUID do cartório>
Authorization: AppToken <chave>      (o contrato declara os dois esquemas)
```

### O que ela é, e o que ela NÃO é

**O CCN é o Cadastro Único de Clientes do Notariado** — a base nacional de
pessoas do Provimento CNJ 149/2023, com dados biográficos, biométricos e
documentos. **Não é a lavratura de ato.**

```
POST /api/uploads                          sobe o arquivo (multipart, até 30 MB)
POST /api/imports                          cria o trabalho de importação
GET  /api/imports                          lista
POST /api/imports/list                     lista com filtro
GET  /api/imports/{id}                     situação
GET  /api/imports/{id}/records             o que entrou
GET  /api/imports/{id}/errors              o que foi recusado
GET  /api/imports/{id}/duplicates          o que já existia
GET  /api/imports/preview/{recordId}       conferir antes
GET  /api/exports/record-sets/{cpf}        buscar pessoa pelo CPF
GET  /api/exports/record-sets/{id}/current a versão corrente
```

**O dado vai em XML, conforme XSD deles.**

**Esta casa tem 4.062 cartões de autógrafo e 462 pessoas com biometria** — e a
biometria do acervo está **danificada na origem** (só 2 dos 436 templates são
base64 válido), com decisão do oficial de colher novas. O CCN é onde essas
pessoas seriam declaradas nacionalmente.

> **UMA ADVERTÊNCIA MEDIDA: o swagger do CCN recusa cliente que não é
> navegador.** `HTTP 403` pelo cliente do sistema, mesmo com cabeçalho de
> navegador; **HTTP 200 dentro do navegador**. Só o documento foi lido assim —
> e **não se sabe se as rotas da API se comportam do mesmo jeito**. Se
> recusarem, o transporte desta casa (que não usa `requests` nem navegador) bate
> nessa parede antes de qualquer credencial. **É a primeira coisa a conferir**,
> e resolve-se com uma chamada em homologação.

**E o e-Notariado é maior que o CCN.** O artigo que o oficial mandou cita ainda
o **CENSEC** (que este sistema já trata em `notas_censec.py`, pelo formato de
arquivo) e o CNB-CF. **Não medi contrato de nenhum dos dois**, e não os declaro.

---

## 5. O QUE JÁ ESTÁ CONSTRUÍDO — para não refazer

| módulo | Central | o que ele faz | o que ele recusa fazer |
|---|---|---|---|
| `cra21_api.py` | CRA-MA | 21 operações medidas no WSDL; testa a ligação, traz o arquivo cru, faz 4 consultas | **10 operações dependem de `userDados`**, que o manual não descreve — declaradas e não chamadas |
| `cenprot_api.py` | CENPROT | 20 caminhos: anuência, certidão, cancelamento, decisão judicial, pedidos, custas | **não lavra ato**; a decisão judicial só se baixa |
| `onrtdpj_api.py` | ONRTDPJ | 10 dos 81: fila, pedido, nota devolutiva, registro, orçamento, cancelamento, teste | **não sobe arquivo** (a casa não tem molde `.odt` do registro) |
| `selador_cliente.py` | FPFTech | o selo, com certificado fixado | — |

**O padrão está estabelecido e é o mesmo para as quatro que faltam:**

1. o contrato baixado para `FONTES_EXTERNAS/`, que não viaja no pacote;
2. um módulo de transporte que **recebe `db` e não `con`** — chamada de rede
   nunca dentro de `BEGIN IMMEDIATE`;
3. a credencial em `centrais_cred`, **fora do banco**;
4. testes que **abrem o contrato e comparam** caminho, método e campo;
5. tela com o prefixo da atribuição, que **diz quando a Central falhou** em vez
   de mostrar lista vazia;
6. e o módulo **não lavra ato** — quem lavra é a casa.

---

## 6. O QUE DEPENDE DO OFICIAL — e é o que trava tudo

Nenhuma das quatro se liga sem credencial, e **nenhuma credencial se pede por
mim**. Em ordem de facilidade:

| # | Central | o que pedir, e onde |
|---|---|---|
| 1 | **ONRTDPJ** | o token, já achado — falta só informar no sistema |
| 2 | **ON-RCPN** (as duas) | cadastro em `home.registrocivil.org.br/solicitacao-novo-client` → token IdRC **único para as duas** |
| 3 | **ONR / RI** | credencial do `POST /v1/auth/token` — o ONR é quem provisiona |
| 4 | **CCN** | `X-Api-Key` e o `X-Subscription` (UUID do cartório) — pelo e-Notariado |

**E três endereços que só a credencial resolve:** o de produção do ON-RCPN, o
manual de autenticação do IdRC (um Google Docs citado nos dois contratos), e o
XSD do CCN.

---

## 7. O QUE EU RECOMENDO, com a razão de cada uma

**A ordem não é por tamanho: é por buraco aberto.**

**1º — ON-RCPN e-Proclamas (3 caminhos). ~~É a menor de todas~~ — FEITO em
03/09/2026.** Era a menor e fechava um buraco declarado. O que a construção
mostrou, e que o planejamento não previa: o dado dos nubentes sai da
**habilitação** e não do assento (o Livro D não aceita pessoa nenhuma), **o
endereço não vai** (seis campos contra um de texto livre), e a matrícula do
Livro D precisou de um dígito que **nenhum manual desta casa tem** — ele veio
do exemplo do contrato, e entrou com a procedência marcada. Ver
`O_EPROCLAMAS_CONSTRUIDO.md`.

**2º — ON-RCPN Certidão (10 caminhos).** É a maior entrega para o balcão: sete
filas de pedidos, incluindo **registro de nascimento das Unidades Interligadas
e de óbito do e-Óbito**. E ela obriga a fechar os achados 2 e 3 do revisor,
porque a Central pede aqueles campos.

**3º — ONR / RI (39 caminhos).** A maior, e a que substitui envio manual de
verdade (`ri_onr` gera arquivo hoje). Faria em **três pedaços**: indicador real,
protocolo/atendimento eletrônico, edital. **Não é um trabalho só.**

**4º — CCN (11 caminhos).** O menor risco de errar e o menor ganho imediato: é
cadastro de pessoa, e não ato. **E tem a parede do 403 para conferir antes.**

> **E há uma coisa a decidir antes de todas**, que é do oficial e não minha: o
> sistema passa a **falar** com quatro Centrais em produção. Hoje ele fala com
> duas, e o balcão ainda não voltou a lavrar. Ligar tudo de uma vez põe quatro
> integrações novas em produção ao mesmo tempo.

---

## 8. AS ARMADILHAS MEDIDAS — uma por contrato

Estas custaram caro nas integrações anteriores. Ficam escritas para não custarem
de novo.

| contrato | a armadilha |
|---|---|
| **ONR / RI** | o `openapi.json` **não é JSON válido** (2 vírgulas antes de fecho); e o `tokenUrl` do `oauth2` é `https://teste/oauth2/token`, endereço que não existe |
| **e-Proclamas** | **CPF sem pontuação e CEP COM hífen** na mesma mensagem; datas `dd/mm/aaaa`; sexo só `masculino`/`feminino`; município IBGE de 7 dígitos |
| **ON-RCPN** | **os dois contratos publicados são de HOMOLOGAÇÃO** e o de produção não aparece |
| **CCN** | o swagger **recusa cliente que não é navegador** (403), e não se sabe se as rotas fazem o mesmo |
| **ONRTDPJ** (já construída) | `consumes: application/form-data`, tipo que não existe; `required` vazio nas 100 definições |
| **CENPROT** (já construída) | três convenções de data, duas de paginação, corpo embrulhado num caminho e cru nos outros |
| **CRA** (já construída) | o WSDL de homologação declara `http://` sem o S, com senha em HTTP Basic |

**E a que vale para todas: `required` vazio não quer dizer «nada é
obrigatório».** No ON-RCPN, na ONRTDPJ e nos `/v2` da CENPROT ele vem vazio, e
a Central recusa do mesmo jeito. **Não se inventa obrigação que o contrato não
declara** — o que a casa recusa é a chamada que não pode funcionar, e o código
diz que isso é regra da casa, não do contrato.

---

## 9. UMA OBSERVAÇÃO DE MÉTODO, e ela é a mais importante deste documento

**Nada disto foi achado por mim.** No mesmo dia 03/09/2026:

- eu escrevi que sobre a Central do RTDPJ **«não havia contrato a medir»** — e o
  contrato estava público, com 81 caminhos;
- o `CLAUDE.md` dizia desde 28/08 que o envio ao e-Proclamas era **«integração
  que este sistema ainda não tem»** — e a API existe desde 10/04/2025;
- `ri_onr.py` diz desde sempre que **«nada aqui transmite arquivo»** — e o ONR
  publica 39 caminhos, com os dois ambientes declarados.

**Três vezes o mesmo erro, e nas três quem mandou procurar noutro lugar foi o
oficial.** A frase que este projeto já tinha — *«coluna vazia não prova que a
coisa não acontece»* — vale para a fonte inteira: **não achar onde eu procurei
não prova que não existe.**

O que desfez não foi releitura. Foi **procurar noutro lugar**.

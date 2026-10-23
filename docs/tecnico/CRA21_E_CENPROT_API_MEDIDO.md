# A API DA CRA21 E A DA CENPROT — o que está medido, e o que falta

> **Atualização de 23/09/2026 — resposta real da homologação recebida.**
> A operação `RemessaPendente` trouxe 3 lotes e 30 títulos em **XML**
> (`<remessa><hd/><tr/><tl/></remessa>`), não o TXT de 600 posições que
> este estudo anterior esperava entregar diretamente ao leitor legado. O
> envelope preservado, as validações e a correção necessária estão em
> [CRA_HOMOLOGACAO_REMESSA_2026-09-23.md](CRA_HOMOLOGACAO_REMESSA_2026-09-23.md).
> Onde este documento disser que o retorno da API já entra diretamente em
> `protesto_arquivo`, prevalece a medição nova: falta um adaptador XML.

Ordem do oficial em 02/09/2026: *«acho que agora poderemos resolver todos
problemas do protesto. vamos integrar a api da cra21»*, e no mesmo dia:
*«também juntei a errata com a API da cenprot, pra complementar»* e
*«protesto é importante, precisamos ser eficientes»*.

**Este documento é a medição, e não a proposta.** Nada aqui foi deduzido: os
dois contratos foram baixados e lidos. Onde não deu para medir, está escrito
que não deu.

As fontes ficam em **`FONTES_EXTERNAS/cra21/`** — que **não viaja no `.cgu`**,
como a doutrina: são 2,2 MB de material de desenvolvimento.

| arquivo | o que é |
|---|---|
| `cra_ma_prod.wsdl` | o contrato da CRA-MA em produção, 18.107 bytes |
| `cra_ma_homolog.wsdl` | o mesmo em homologação, 18.102 bytes |
| `cenprot_doc_api.pdf` | «Operação API Resolve», IEPTB, versão 1.0 de 29/02/2024 |
| `cenprot_auth.pdf` | «API Resolve: Manual de Autenticação» |
| `cenprot_errata_comunicado_007_2024.pdf` | o comunicado que o oficial trouxe |

---

## PARTE 1 — A CRA21 (SOAP)

### Onde ela está, e os dois ambientes

| | |
|---|---|
| **produção** | `https://crama.crabr.com.br/crama/xml/protestos_cartorio.php?wsdl` |
| **homologação** | `https://crama.cra21.com.br/crama/xml/protestos_cartorio.php?wsdl` |

O `crama` é o Maranhão: o padrão do manual é `craUF`. **Os dois WSDL estão
públicos e responderam HTTP 200** em 02/09/2026, sem credencial nenhuma — foi
assim que este contrato se mediu.

### **E O WSDL DE HOMOLOGAÇÃO DECLARA `http://`, SEM O S**

Medido linha a linha: os dois arquivos são **idênticos**, com as **mesmas 21
operações**, e a única diferença real é o endereço do serviço:

```
produção     <soap:address location="https://crama.crabr.com.br:443/crama/xml/protestos_cartorio.php"/>
homologação  <soap:address location="http://crama.cra21.com.br/crama/xml/protestos_cartorio.php"/>
```

**O manual diz que HTTPS é obrigatório, e o WSDL de homologação diz o
contrário.** Quem montar o cliente lendo o WSDL — que é o normal — vai falar
**em texto puro** com a Central. E a autenticação desta API é **HTTP Basic**:
a senha do cartório viajaria legível na rede.

**Consequência para o código: o endereço não se lê do WSDL — ele se força para
HTTPS.** É a mesma decisão do selador, onde o certificado se fixa em vez de se
ignorar: quando a rede é o meio, quem decide o transporte é a casa.

### A autenticação

**HTTP Basic**, no cliente SOAP. Medido no exemplo em PHP do manual:

```php
$options = array('soap_version' => SOAP_1_1, 'login' => $login, 'password' => $senha);
$client = new SoapClient("...?wsdl", $options);
```

**Não há parâmetro de usuário nas operações** — nenhuma das 21 recebe login,
senha ou código de cartório. Quem identifica a serventia é a credencial HTTP.

> **E ela não entra no banco**, pela mesma razão da senha do selador e da chave
> do Claude: o banco viaja no backup, e o backup já saiu da serventia. O lugar
> é `%PROGRAMDATA%\CartorioGestao\`, ao lado de `selador.cred`.

### As 21 operações, com os parâmetros medidos do WSDL

Todos os parâmetros são `string`, e toda resposta é um `return` `string`.

| operação | parâmetros | o que faz (do manual) |
|---|---|---|
| `Remessa` | `userArq`, `downloadImagem` | traz as remessas da data do arquivo **mais as pendentes de datas anteriores** |
| `RemessaPendente` | `userArq`, `downloadImagem` | traz **todas** as pendentes, sem olhar data nem apresentante |
| `Confirmacao` | `userArq`, `userDados` | envia a confirmação |
| `Retorno` | `userArq`, `userDados` | envia o retorno |
| `Desistencia` | `userArq` | traz as desistências da data e as pendentes |
| `Cancelamento` | `userArq`, `downloadImagem` | traz os cancelamentos da data e os pendentes |
| `Autorizacao` | `userArq`, `downloadImagem` | traz as autorizações (de retirada e de cancelamento) |
| `BuscarApresentante` | — | lista os apresentantes |
| `Imagem` | `userArq`, `userDados` | envia imagem |
| `ConsultaSlip` | `protocolo`, `dataProtocolo` | consulta o slip |
| `ConsultaAutorizacao` | `userArq`, `protocolo`, `dataProtocolo`, `marcarBaixado` | consulta uma autorização; **marca como baixada salvo se `marcarBaixado` for `0` ou `false`** |
| `ConsultaImagem` | `nossoNumero`, `numeroTitulo`, `documentoDevedor`, `saldoTitulo`, `vencimento`, `remessa` | acha a imagem de um título |
| `Intimacao` | `userArq`, `userDados` | **intimação eletrônica** |
| `ConsultaIntimacao` | `userDados` | consulta a intimação |
| `AvisoAutorizacao` | `userArq`, `userDados` | aviso de autorização |
| `ConsultaAvisoAutorizacao` | `userDados` | consulta o aviso |
| `CustasTitulo` | `userArq`, `userDados` | **as custas do título** |
| `TituloComplemento` | `userArq`, `userDados` | dados complementares do título |
| `AutorizacoesEfetivadas` | `userDados` | as autorizações já efetivadas |
| `ConsultaAutorizacoesPeriodo` | `dataInicioSolicitacao`, `dataFimSolicitacao`, `dataInicioRemessa`, `dataFimRemessa` | autorizações por período |
| `OrdemCancelamento` | `userArq` | **a ordem de cancelamento** |

### **`userArq` É O NOME DO ARQUIVO, E NÃO O CONTEÚDO** — e isso muda tudo

Medido na página *Download e Consulta* do manual: *«Nome do arquivo no formato
FEBRABAN»*. O exemplo em PHP confirma:

```php
$retornoXml = $client->Confirmacao('C0013110.141');
```

**Isto é a peça que encaixa com o que este sistema já tem.** O módulo
`protesto_arquivo.py` lê **e escreve** os cinco formatos, medido em 697
arquivos reais com ida e volta byte a byte; `protesto_remessa.py`,
`protesto_retorno.py` e `protesto_desistencia.py` montam e consomem esses
arquivos. **O que a API acrescenta não é o formato: é o transporte.** Hoje o
escrevente baixa e sobe pelo site; com a API, o sistema faz isso sozinho.

> **E o que vai em `userDados` NÃO ESTÁ MEDIDO.** O manual não o descreve, e o
> exemplo em PHP passa só um argumento. A hipótese razoável é o conteúdo do
> arquivo, mas **hipótese não se escreve em código que fala com a Central** —
> isso se resolve com **uma chamada em homologação**, que é justamente o que a
> P21 ofereceu.

### Outros valores medidos

- `downloadImagem`: **`1`** baixa a imagem, **`2`** só confere se ela existe.
- O nome do arquivo de desistência começa com **`DP`**; o de autorização, com
  **`AC`** ou **`AD`**.
- Na `Autorizacao`, o atributo **`t07`** diz o tipo: **`C`** cancelamento,
  **`S`** retirada (do inglês *sustação*? **não medido** — o manual só dá as
  letras).
- Limites do servidor: **100 MB** por arquivo, **30 minutos** de tempo limite.

---

## PARTE 2 — A API RESOLVE DA CENPROT (REST/JSON)

Do manual *Operação API Resolve*, IEPTB, versão 1.0 de 29/02/2024. **É outra
coisa que a CRA**: aqui não há arquivo FEBRABAN — é JSON, e o assunto é
**certidão e anuência**.

### Onde ela está

Base: `https://wspub.cenprotnacional.org.br/ieptb-cenprot-api-cartorio`

| verbo | caminho | o que faz |
|---|---|---|
| POST | `/token` | autentica e devolve o token |
| GET | `/certidoes` | os pedidos de certidão **pendentes** do cartório |
| GET | `/anuencias` | os pedidos de anuência **pendentes** |
| POST | `/certidao/processar` | devolve o orçamento — e a certidão quando pronta |
| POST | `/anuencia/processar` | aprova com valor, ou recusa com motivo |

Swagger: `https://wspub.cenprotnacional.org.br/ieptb-cenprot-api-cartorio/swagger`

> **O JSON do Swagger não está nos caminhos de sempre.** Tentados em
> 02/09/2026: `/swagger/v1/swagger.json`, `/swagger.json`, `/v3/api-docs`,
> `/openapi.json`, `/swagger/index.html` — **os cinco devolveram 404**. O
> manual em PDF diz que «replica as funcionalidades descritas no Swagger», e é
> ele que serve de contrato até alguém abrir a página com navegador.

### A autenticação, e onde ela se cadastra

**Usuário e senha, cadastrados pelo próprio cartório na CENPROT** — não vêm de
fora. O caminho é: **Cadastro → Cadastro do Cartório → «Informações de
Autenticação da API» → Editar usuário**.

Padrão mínimo exigido pela CENPROT: **8 caracteres**, com maiúscula, minúscula,
número e caractere especial.

**Isto é passo do oficial, e não do sistema** — como o cadastro no INFODIP.

### O que cada resposta traz

**Certidão** (`GET /certidoes`): `cd_pedido`, `dt_pedido`, `vlr_emolumentos`,
**`nm_chave_verificacao`** (a chave única do protesto — a mesma de 23 dígitos
que `protesto_cenprot.py` já sabe ler), `cd_status`, `nm_status`, mais
`dados_solicitante` (nome, documento, telefone, celular, endereço) e
`dados_certidao` (o devedor).

**Anuência** (`GET /anuencias`): `cd_anuencia`, `nm_chave`,
**`ds_anuencia_pdf_b64`** e **`ds_anuencia_anexo_pdf_b64`** (o PDF da anuência
e o comprovante, em base64), `nm_nr_protocolo`, `dt_protocolo`,
`nm_nr_documento_devedor`, `nm_devedor`, `vl_protesto`,
`dt_solicitacao_anuencia`, `nm_nr_titulo`, `nm_nr_documento_credor`,
`dt_emissao`, **`nm_assinatura`** e **`assinatura_validade`**, mais
`dados_solicitante` e `dados_cartorio`.

> **A ANUÊNCIA VEM ASSINADA, E O `nm_assinatura` É UM e-CPF DA ICP-BRASIL.** O
> exemplo do manual traz `CN=FULANO DA SILVA:00000000000,OU=RFB e-CPF A3,…` —
> **exatamente a forma que `assinatura_digital.py` já lê** dos seis
> instrumentos reais desta casa. A peça de conferir quem assinou já existe.

### O que se manda de volta

`POST /certidao/processar`: `cd_pedido`, `vl_orcamento`. E **quando o status
for «Aguardando certidão»**: `nm_status` mais `arquivo_certidao` (o PDF).

`POST /anuencia/processar`: todos os campos do título (`nm_nr_protocolo`,
`dt_protocolo`, `nm_nr_documento_devedor`, `nm_devedor`,
`dt_solicitacao_anuencia`, `nm_nr_titulo`, `nm_nr_documento_credor`,
`dt_emissao`, `nm_chave`) mais **`ic_aprovado`**:

- `true` → **`vl_custas` é obrigatório**;
- `false` → **`motivo_recusa` é obrigatório**.

**Todos os parâmetros devem ser preenchidos** — é o manual que diz.

Códigos: `200` OK · `401` falha de autenticação · `404` não encontrada ·
`500` erro no processamento.

> **«As requisições serão executadas diariamente pelo IEPTB»** — está no
> manual, sobre a certidão. Ou seja: **há um relógio do outro lado**, como as
> 11h30 da CRA. Quem não responder no dia não responde.

---

## PARTE 3 — O QUE ISSO FECHA DO ROTEIRO

O sistema declara **8 dos 16 passos** das Centrais (`protesto_roteiro.py`).
Cruzando os oito que faltam com as duas APIs:

| passo que falta | quem resolve | como |
|---|---|---|
| CRA — recebimento de **cancelamento** | **CRA21** | `Cancelamento`, `OrdemCancelamento` |
| CRA — recebimento de **AC** (autorização) | **CRA21** | `Autorizacao`, `ConsultaAutorizacao`, `AutorizacoesEfetivadas`, `ConsultaAutorizacoesPeriodo`, `AvisoAutorizacao` |
| CRA — **boleto de repasse** | **ninguém** | não há operação no WSDL, e o verificador do código de barras continua sem se explicar |
| CENPROT — remessa pela Central | **não** | a API Resolve é só certidão e anuência |
| CENPROT — XML diário dos apontados | **não** | idem |
| CENPROT — instrumento eletrônico | **não** | idem |
| CENPROT — **pedidos de anuência** | **CENPROT** | `GET /anuencias` + `POST /anuencia/processar` |
| CENPROT — pedido de **cancelamento** | **em parte** | a anuência é o que o precede; o ato continua sendo lavrado na ficha |

**E há o que não estava no roteiro e a CRA oferece:**

- **`Intimacao` e `ConsultaIntimacao`** — intimação **eletrônica**. Esta casa
  intima **1.115 por edital contra 61 em mãos**; se a eletrônica valer aqui,
  ela mexe no passo mais caro do módulo.
- **`CustasTitulo`** — as custas pela própria Central. Este projeto reconstruiu
  a receita da retirada e do cancelamento a partir de 375 títulos, e acertou
  166 de 173 no centavo. **Com esta operação, o número deixa de ser derivado.**
- **`TituloComplemento`** — os dados complementares do devedor. E o **item II
  do art. 22** (o endereço do apresentante) hoje sai **declarado em falta** no
  instrumento de protesto, porque não está em fonte nenhuma. **A conferir se
  esta operação o traz.**
- **`ConsultaSlip`**, **`ConsultaImagem`**, **`BuscarApresentante`**.

---

## PARTE 4 — O QUE FALTA PARA COMEÇAR

**A P21 ofereceu, por mensagem de 02/09/2026 (Pessoa Exemplo, P21 Sistemas):**

> *«tendo feito a criação da integração com a CRA, basta liberar para eles o
> usuário e senha de homologação. Caso eles queiram títulos de exemplo,
> podemos enviar conforme for solicitado. Podemos liberar um ambiente de
> teste.»*

### O que o oficial precisa pedir/fazer

1. **Usuário e senha de HOMOLOGAÇÃO da CRA** — é o que destrava tudo. Sem
   credencial não há uma chamada, e sem uma chamada o `userDados` continua sem
   medição.
2. **Títulos de exemplo** em homologação — a P21 se ofereceu, e neste projeto
   **mais amostra fechou quatro lacunas de layout** que engenhosidade nenhuma
   fechou.
3. **Cadastrar o usuário da API na CENPROT** — Cadastro → Cadastro do Cartório
   → «Informações de Autenticação da API». Só ele pode.
4. **Abrir o Swagger da CENPROT no navegador** e salvar o JSON, se a página o
   oferecer: o contrato legível por máquina vale mais que o PDF.

### O que fica decidido antes de escrever a primeira linha

- **O endereço vai forçado para HTTPS**, e não lido do WSDL — ver o achado
  acima. Senha de cartório não viaja em texto puro.
- **A credencial não entra no banco** — arquivo em `%PROGRAMDATA%`, como a do
  selador.
- **Homologação primeiro**, e a base é configuração e não constante: é a mesma
  decisão do selador, que não assume a base.
- **A chamada de rede nunca acontece dentro de `db.transaction()`** — a regra
  que existe desde o selador, e aqui vale igual: um `BEGIN IMMEDIATE` segurado
  por trinta segundos de rede põe a casa inteira no `busy_timeout`.
- **Nada se lavra sozinho.** A API traz e leva arquivo; quem aponta, protesta,
  cancela e certifica continua sendo o módulo de domínio, com as recusas que
  ele já tem. É a regra do CNIB: *avisar e preparar, ficando pendente o okay*.

---

## O que este documento NÃO afirma

- **Não sei o que vai em `userDados`.** O manual não diz e o exemplo não
  mostra. Uma chamada em homologação responde.
- **Não sei se a intimação eletrônica da CRA vale no Maranhão** — a operação
  existe no contrato; se a norma estadual a admite é outra pergunta, e é do
  oficial.
- **Não abri o Swagger da CENPROT**: os cinco caminhos de sempre devolveram
  404, e o que há é o PDF.
- **Não testei uma única chamada** — nem em homologação. Sem credencial não há
  o que testar, e chutar credencial contra a Central não se faz.

---

# PARTE 5 — O QUE FOI CONSTRUÍDO EM 02/09/2026, E O QUE A MEDIÇÃO DESMENTIU

Ordem do oficial: *«pode seguir na construção»*, e antes disso *«siga até
terminar, vá com calma e cuidado»*.

Está de pé: `centrais_cred.py` (a senha, fora do banco), `cenprot_api.py` (o
transporte), `cn_schema.py` + `cenprot_pendencias.py` (o domínio) e
`cenprot_web.py` + duas telas. Os testes que mais valem **abrem o
`swagger.yaml` e comparam** — não conferem contra a minha lembrança.

## Os seis defeitos que só a medição pegou

Eu escrevi o módulo, reli duas vezes, e ele me pareceu certo nas duas. **Todos
os seis falhariam CALADOS** — parâmetro que a Central não conhece ela ignora, e
campo que falta ela devolve num 500 que não diz qual.

### 1. A MESMA API USA TRÊS CONVENÇÕES DE DATA E DUAS DE PAGINAÇÃO

Eu escrevi as três iguais, e errei nas três.

| rota | como ela chama |
|---|---|
| `/v2/anuencias`, `/v2/certidoes`, `/renegociacoes` | `data_inicio` · `data_fim` · `pagina` |
| `/cancelamento/pedidos` | `dt_inicio` · `dt_fim` — **os dois obrigatórios** |
| `/decisao-judicial/pendentes` | `dt_ocorrencia_de` · `dt_ocorrencia_ate` · `page` · `per_page` |
| `/anuencia/arquivos` | `cd_anuencia` (inteiro) — e **não** a chave do protesto |
| `/pedidos/consulta` | `nr_pedido` · `data_pedido` (ao menos um) |

**O estrago seria a tela pedir «só as de setembro» e receber o período
inteiro, sem erro em lugar nenhum.**

### 2. `/v2/certidao/processar` EXIGE TRÊS CAMPOS, E EU CONFERIA UM

`required: [cd_pedido, vl_orcamento, arquivo_certidao]`, e eu conferia só o
`cd_pedido`. **O que faltava era `vl_orcamento`, que é dinheiro** — é o número
que o solicitante vê.

**E o terceiro se contradiz dentro do próprio contrato**, o que fica declarado
em vez de resolvido por palpite: a lista `required` põe `arquivo_certidao` como
sempre obrigatório, e a descrição, duas linhas acima, o condiciona ao status
«aguardando certidão». **Exigi-lo sempre travaria o orçamento**, que é o
primeiro passo e no qual a certidão ainda não existe.

### 3. `/v2/anuencia/processar` EXIGE DOZE CAMPOS, E EU CONFERIA DOIS

O schema do `v2` lista as propriedades e **não** declara quais são
obrigatórias. Quem responde são duas fontes do mesmo arquivo: a descrição dele
(«cd_anuencia, ic_aprovado e os **dados do protocolo e devedor**») e o gêmeo
legado `/anuencia/processar`, que marca `required: true` em doze parâmetros.

A conferência existe porque **a Central responde 500 sem dizer qual item
faltou**; conferindo dois, o balcão continuaria levando o 500 mudo pelos outros
dez.

### 4. `/pedidos/consulta` E `/pedidos/protocolar` SÃO A REMESSA DA CENPROT

**É o passo 1 do roteiro das Centrais**, que estava marcado «no site da
CENPROT» com `tela: None`. A Central manda o pedido, a casa aponta, e devolve o
número do protocolo e a chave única.

**E O `GET` NÃO DEVOLVE A CHAVE ÚNICA QUE O `POST` EXIGE** — medido: o
`/pedidos/consulta` não a traz em campo nenhum da resposta. Ela vem do **XML
diário**, que `protesto_cenprot` já lê, casando a chave com o nosso protocolo
em 175 de 175. O módulo **recusa** protocolar sem ela, dizendo onde consegui-la.

### 5. O CORPO VAI EMBRULHADO NUM CAMINHO E CRU NOS OUTROS DOIS

```
/v2/anuencia/processar   type: array   -> o corpo E a lista
/v2/certidao/processar   type: array   -> o corpo E a lista
/pedidos/protocolar      type: object  -> {"pedidos": [...]}
```

**Esta é a correção mais cara deste projeto, pelo outro lado.** Eu embrulhava o
pedido de selo em `{"dadosSelo": …}` porque a documentação nomeava o parâmetro
de corpo, e com o embrulho **nenhum selo automático sairia, em atribuição
nenhuma**. A lição não é «nunca embrulhe»: é **leia o schema de cada caminho**.

E os tetos de lote também não são iguais: **1.000** nos `processar`, **50** no
`protocolar`.

### 6. `/cancelamento/pedidos` NÃO DEVOLVE `cd_pedido` — E O `POST` O EXIGE

A resposta traz `nr_pedido` e `cd_pedido_cartorio`; o
`/cancelamento/cancelar-protesto` pede `cd_pedido`, «ID do pedido (tabela
pedidos) **obtido via GET /cancelamento/pedidos**».

Quem desempata são os **exemplos do próprio contrato**, que trazem números
diferentes de propósito:

```
POST cd_pedido            example: 1000001
GET  nr_pedido            example: 1000001     <- bate
GET  cd_pedido_cartorio   example:  100001     <- nao bate
```

Mais o nome: `cd_pedido_cartorio` é o código **do cartório** para aquele pedido,
que é outra coisa. **Um caso que separa vale mais que cinco que concordam** — a
mesma régua que decidiu o `numerotitulo` do edital.

**ISTO FICA «A CONFERIR» NA HOMOLOGAÇÃO**, e é para isso que ela serve. A tela
mostra o número antes de mandar e diz de onde ele saiu.

## Dois erros de digitação DO CONTRATO, e os dois são armadilha

1. **`/custas/arquivo`** declara, na lista `required`, o segundo campo **entre
   aspas e com dois espaços no fim**, enquanto a propriedade, logo abaixo, se
   chama `base64_arquivo`. Quem copiar o nome da lista manda um campo que a
   Central não conhece.
2. **`/pedidos/protocolar`** declara a chave única com `minLength: 23,
   maxLength: 23` e dá como exemplo `SP12345678900000000000123`, que tem
   **25 caracteres e começa com letras**. Vale a restrição, que bate com o dado
   real desta casa: `2198765 · 01412433 · 01 · 260417` = **23 dígitos**.

## O que isto fechou do roteiro das Centrais

O sistema fazia **8 dos 16 passos**; agora faz **11**.

| passo da CENPROT | antes | agora |
|---|---|---|
| 1. Recebimento de remessa (Gestão de Pedidos) | sem tela | `protesto_pendencias` |
| 4. Pedido de certidão eletrônica | a certidão se emitia aqui | o **pedido** chega pela API |
| 5. Pedidos de anuência | sem tela | `protesto_pendencias`, com os PDFs assinados |
| 6. Pedido de cancelamento | sem tela | `protesto_pendencias` (informa; **não lavra**) |
| 8. Arquivo de emolumentos | baixava à mão | **sobe pela API**, mesmo arquivo |

**E o roteiro foi atualizado junto** — buraco fechado que continua declarado é
o carimbo que mente.

## O que o sistema RECUSA fazer, e por quê

- **Não lavra ato nenhum.** O cancelamento se lavra na ficha do título, com
  hipótese do catálogo e fundamento escrito. A tela apenas **informa** a
  Central do que já foi lavrado. É a regra do CNIB pela quarta vez.
- **A decisão judicial só se BAIXA.** O
  `/decisao-judicial/processar/{nm_chave}` existe e **não é chamado**: quem
  registra a ordem — com o juízo, o processo e a **data do recebimento**, que é
  de onde corre o prazo do § 2º do art. 17 — é o oficial. Ela aparece na fila
  para o balcão saber que existe, e para o título não ser oferecido no
  «A protestar» sem que ninguém veja a ordem.
- **`renegociacoes()` foi APAGADA, e não desligada.** Escrevi a função porque o
  caminho está no contrato, e **nenhuma tela a chamava** — o defeito mais
  repetido deste projeto, seis vezes contadas. As renegociações não estão no
  roteiro que o oficial trouxe. **O caminho fica declarado em `CAMINHO`**, para
  ninguém o reinventar achando que sumiu.

## O ambiente entra na chave, e isso não é detalhe

A homologação e a produção devolvem códigos do **mesmo intervalo**:
`cd_anuencia = 1` existe nas duas. Sem o ambiente na chave única de
`cn_pendencias`, a primeira anuência de teste ocuparia o lugar da primeira
anuência de verdade, e **a de verdade não entraria, sem erro em lugar nenhum**.

E a tela **grita** qual é qual: pendência de teste com cara de real é o carimbo
que mente na pior forma possível, porque quem a lê vai ao balcão dizer que
existe.

## Três coisas que o desenvolvimento errou, e o teste pegou

1. **Falta de credencial virava HTTP 500** na cara do escrevente. As rotas
   apanhavam `PendenciaError` e `CenprotError` e **não** `CredencialError` —
   erro de regra não é HTTP 500, e eu quebrei a regra em cinco rotas de uma
   vez. Agora há uma lista só, `RECUSAS_DO_BALCAO`. **E há duas classes com o
   mesmo nome nesta casa**: `cenprot_api.CenprotError` é `RuntimeError` e
   `protesto_cenprot.CenprotError` é `ValueError` — quem apanhar uma achando
   que apanha a outra deixa passar a que importa.
2. **O varredor do roteiro lia UM arquivo escrito à mão** (`atribuicoes_web.py`)
   e acusou «a rota não existe» sobre rotas que existem, só porque nasceram em
   `cenprot_web.py`. É a lição do `MODULOS_COM_SECAO` pela segunda vez — e
   dentro do teste que deveria guardar a regra.
3. **O meu varredor de função órfã contava só chamador de fora** e acusou três
   que o próprio módulo usa. Varredor que acusa o certo é varredor que ninguém
   lê na terceira vez.

## O que ainda espera o oficial

- **A credencial da CENPROT**, digitada por ele em Administrativo →
  Configurações → Centrais de Protesto. Ela vai para
  `%PROGRAMDATA%\CartorioGestao\cenprot.cred`, **fora do banco** — o banco
  viaja no backup, e o backup já saiu da serventia.
- **O usuário e a senha de homologação da CRA**, que a P21 (Pessoa Exemplo) ofereceu
  liberar, mais os títulos de exemplo e o ambiente de teste.
- **Conferir na homologação** o `nr_pedido`/`cd_pedido` do cancelamento.

---

# PARTE 6 — A CRA CONSTRUÍDA, E O QUE ELA RECUSA FAZER

`cra21_api.py` (o transporte SOAP) e `cra21_web.py` + `protesto_cra_api.html`
(a tela), de 02/09/2026.

## O que se mediu no WSDL, e virou teste

**O juiz é o próprio arquivo**, e não a minha lembrança: os testes abrem os
dois WSDL e comparam. As **21 operações e os parâmetros de cada uma, na
ordem** — e a ordem importa: em SOAP `rpc/encoded` os parâmetros são
**posicionais** dentro do elemento da operação, e trocar `protocolo` com
`dataProtocolo` faria a Central responder sobre outra coisa **sem erro
nenhum**.

## **O NAMESPACE MUDA COM O AMBIENTE**, e isso não é detalhe

```
produção     urn:crama.crabr.com.br
homologação  urn:crama.cra21.com.br
```

Num cliente que monta o envelope à mão — que é o caso, porque esta casa não usa
biblioteca SOAP —, **com o namespace errado a Central não reconhece a
operação**, e a recusa não diz por quê. Os dois estão medidos, um por ambiente,
e há teste que os compara com o `targetNamespace` de cada arquivo.

## O `https` se força, e o teste guarda o achado

O WSDL de homologação declara `http://`, sem o S. **O guarda do módulo recusa**
— e há teste que **falha se eles consertarem o arquivo**, para que a correção
não passe despercebida. O endereço forçado aponta para o **mesmo servidor**:
forçar HTTPS é mudar o transporte, e não o destino.

## O que a tela faz, e o que ela declara que não sabe

**Duas coisas do contrato não estão medidas**: o que vai em `userDados` e o que
exatamente volta no `return`. O manual não descreve nem uma nem outra, e o
exemplo em PHP passa **um argumento só**.

**Construir a corrente inteira em cima disso seria inventar o meio dela.** Um
botão «baixar a remessa e apontar tudo» que lesse errado o que a Central manda
**apontaria títulos que ninguém apresentou** — e apontamento não se desfaz.

Então a tela faz o que dá para fazer com verdade:

| o que ela faz | como |
|---|---|
| **testa a ligação** | `BuscarApresentante`, a **única operação sem parâmetro nenhum** |
| **traz o arquivo cru** | remessa, pendentes, desistências, cancelamentos, autorizações, ordem de cancelamento |
| **consulta** | slip, autorização, imagem de título, autorizações do período |
| **declara o que falta** | as **dez** operações que dependem de `userDados`, com nome e tudo |

**O teste de conexão não pode ser uma remessa.** Um teste que pedisse uma
remessa **marcaria a remessa como baixada** do lado de lá, e o dia seguinte
começaria com o arquivo faltando. `BuscarApresentante` não afirma nada sobre
arquivo — e é a única assim.

**E CONSULTAR AUTORIZAÇÃO MARCA COMO BAIXADA**, salvo se se disser que não —
está no manual. O padrão do sistema é **não marcar**: uma consulta que muda o
estado da Central não pode ser o que um botão de olhar faz calado. A caixa
está na tela, e quem marca, marca de propósito. **O teste lê o
`<marcarBaixado>` do envelope**, e não o padrão da assinatura — o que a
Central recebe é o envelope.

## O que a Confirmação e o Retorno esperam

São os **dois passos com hora marcada** do roteiro — 11h30 e 14h10 — e os dois
dependem de `userDados`. **Eles não têm botão**, e a tela diz isso com o nome
das operações à vista. **É este o último nó**, e ele se desata com **uma
chamada em homologação** — que é justamente o que a P21 ofereceu liberar.

## O roteiro das Centrais: de 8 para 13 dos 16 passos

| | antes | agora |
|---|---|---|
| CRA | 5 de 8 | **7 de 8** |
| CENPROT | 3 de 8 | **6 de 8** |

**Os três que sobram, e por que sobram:**

1. **Boleto de repasse dos títulos pagos** (CRA) — o verificador do código de
   barras desta casa **não se explicou**: busca exaustiva das 9⁴ combinações de
   pesos, módulo 10 e 11, nas duas convenções, com melhor acerto de **465 em
   1.618** — nível de acaso. Código errado é dinheiro no lugar errado.
2. **Envio do XML diário dos apontados** (CENPROT) — **não há endpoint** na API
   Resolve para isso. O sistema **lê** esse arquivo (é dele que vem a chave
   única); gerá-lo ainda não.
3. **Envio do instrumento de protesto eletrônico** (CENPROT) — também sem
   endpoint. O instrumento **existe** desde 01/09/2026, com os dez itens do
   art. 22 conferidos; o que falta é o caminho de subida.


---

# PARTE 7 — TRÊS COISAS QUE FALTAVAM AMADURECER

O oficial perguntou, em 02/09/2026: *«está pronto? nada mais a amadurecer?»*.
**Havia três, e as três são o mesmo defeito que esta casa já pagou dez vezes:
a peça pronta que ninguém chama.** Nenhuma delas apareceu na releitura;
apareceram quando a pergunta foi feita e eu fui medir.

## 1. O valor da retirada era digitado à mão

`/pedidos/protocolar` exige `vl_retirada`, e a tela mandava o oficial digitá-lo.
**`protesto_cenprot.precos_do_titulo` já o calcula** — a constante somada da
tabela mais a faixa do item 17.4 pelo valor do título, **166 de 173 no
centavo**, medido no arquivo do ano que o oficial baixou do E-Ofício.

Agora ele vem preenchido, **como sugestão**, com a frase que diz de onde veio —
a mesma regra da receita de custas e da participação das partes na DOI:
**não é orçamento fechado, e a tela diz isso**. Quem confirma é quem atende.

**E `None` não vira zero.** Título que não casou, vigência que falta, valor
fora de faixa: os três devolvem `None` **com o motivo escrito**, e não zero.
Zero num campo de dinheiro é uma afirmação — «não custa nada» — e o devedor
viria ao balcão com ela.

**A conta é a MESMA função**, e não uma parecida: há teste que troca
`precos_do_titulo` por uma espiã e confere que foi ela quem calculou, com o
valor e a vigência certos. Uma segunda conta divergiria no primeiro conserto,
e o que ela calcula é o que o devedor paga.

## 2. O roteiro não contava os três passos que ganharam tela

Eles ficaram com `medida: None`: a tela existia e a coluna «hoje» ficava
vazia. **Roteiro que não conta um passo que ele passou a fazer** é meia
verdade — pior que a declaração honesta de que não faz.

Entraram `anuencia_baixada`, `cancelamento_cenprot_baixado` e
`pedido_protesto_baixado`, com a **mesma régua dos passos antigos**: contam o
que **ENTROU hoje**, e não o que espera.

**São duas perguntas diferentes, e responder uma com a outra estragaria as
duas.** O roteiro conta o que já aconteceu — a coluna zera todo dia, e é isso
que faz o escrevente olhar. `cenprot_pendencias.painel` conta o que espera, e
esse número não zera sozinho. Há teste que confere que o dia seguinte começa
em zero.

**E a faixa de data é a mesma dos outros**, e não um recorte de texto no SQL:
o teto de acoplamento deste módulo é **zero**, e o varredor já me pegou duas
vezes nele.

## 3. A decisão gravada e não enviada não aparecia em «o que ficou pelo caminho»

Ela é **exatamente** isso: alguém olhou a pendência, decidiu, e **a Central
ainda não sabe**. Sem a fonte, ficava esperando numa tela que só quem se
lembra dela abre.

Entrou em `inacabados.FONTES` como `CENPROT_DECIDIDA`, com **prazo de 1 dia** —
o roteiro das Centrais tem hora marcada, e decisão que dorme um dia é o
apresentante sem resposta com o título aparecendo protestado na Central.

**O acervo não entra, e a razão fica escrita**: `cn_pendencias` nasceu em
02/09/2026 e só recebe o que a API baixa — não há uma linha de acervo nela, e
nunca haverá.

E há teste que confere as três coisas que a fonte precisa acertar: que a
pendência **sem decisão** não aparece (não é «inacabada», é «não começada»),
que a **decidida** aparece, e que o `id` devolvido é o que a **tela dela**
espera — devolver outro produziria um link que abre a ficha errada, e ninguém
desconfia de uma ficha que abre.

---

## E a pergunta sobre o «ambiente de testes»

Perguntaram ao oficial se não seria melhor pegar um usuário de ambiente de
testes **antes** da senha de homologação.

**Medido nos dois contratos: cada Central declara exatamente DOIS ambientes**,
e o de teste é a homologação — não são coisas diferentes.

```
CRA        https://crama.crabr.com.br      produção
           https://crama.cra21.com.br      homologação
CENPROT    .../ieptb-cenprot-api-cartorio          "Ambiente de produção"
           .../ieptb-cenprot-api-cartorio-homolog  "Ambiente de homologação"
```

**Não há um terceiro a pedir antes.** E não há risco em receber a de
homologação primeiro: o sistema começa nela por padrão, força HTTPS, e a tela
avisa em vermelho quando o ambiente é o de produção.

**A ressalva que vale**: se o «ambiente de teste» oferecido for o sistema **da
P21**, e não a homologação da Central, ele não serve para esta integração — o
código fala **direto com a Central**, e não passa pela P21.

## E os títulos de exemplo NÃO são dispensáveis

Mas não pelo motivo óbvio. **O formato dos arquivos da CRA já está medido** —
697 arquivos reais, ida e volta byte a byte. Títulos de exemplo não
acrescentam nada a isso.

O que eles resolvem é outra coisa. Faltam **duas** medições, e elas se separam:

| o que falta | o que basta para medir |
|---|---|
| o que a API **devolve** no `return` | a credencial, e qualquer remessa pendente |
| o que vai em **`userDados`** | **um título para confirmar e retornar** |

**O segundo é o que trava a Confirmação e o Retorno**, os dois passos com hora
marcada (11h30 e 14h10). **Sem título na homologação não há o que confirmar
nem o que retornar**, e esse nó fica onde está.

Os dois se desatam no mesmo gesto: **credencial e títulos, juntos.**

# AS APIs DO ON-RCPN — medidas, e elas vão muito além do e-Proclamas

Escrito em **03/09/2026**, a partir de duas mensagens do oficial:

> «tem api no rcpn também: `onrcpn.org.br/nova-api-do-registro-civil-moderniza-envio-ao-e-proclamas-e-geracao-do-livro-d-eletronico/`»
>
> «pesquise se ela não foi ampliada para mais atos»

**Ele estava certo em perguntar.** São **duas APIs**, e a segunda cobre a
certidão inteira do Registro Civil e as filas de pedidos de sete módulos.

Os dois contratos estão guardados em `FONTES_EXTERNAS/onrcpn/`, que **não viaja
no `.cgu`**, e foram baixados dos endereços públicos — como o WSDL da CRA e o
swagger da ONRTDPJ.

---

## 1. A que o oficial apontou — API e-PROCLAMAS

| | |
|---|---|
| contrato | `https://servicosh.registrocivil.org.br/api/proclama/doc/` |
| versão | Swagger **2.0** · «API e-PROCLAMAS 1.0.0» |
| host | `servicosh.registrocivil.org.br` · `basePath: /` · `schemes: [https]` |
| caminhos | **3** |
| lançada em | 10/04/2025 — o Web Service antigo ficou 90 dias no ar |

```
GET   /api/proclama/health              verifica disponibilidade
POST  /api/proclama/enviar              recebe LOTE de proclamas
GET   /api/proclama/recibo/:matricula   recibo em PDF base64
```

**ELA ESTÁ NO AR, e isso foi conferido**: `GET /api/proclama/health` respondeu
**HTTP 200** com o corpo `Conexão com Oracle realizada com sucesso`.

### O e-Proclamas e o Livro D são DOIS BOOLEANOS DO MESMO ENVIO

É o que responde à pergunta do oficial pelo lado desta API. No corpo de
`/api/proclama/enviar`, cada proclama traz:

```
publicacao        boolean    →  publica no e-Proclamas
livro_eletronico  boolean    →  gera o Livro D Eletrônico
```

**Uma chamada faz as duas coisas.** O Livro D é o que foi acrescentado.

### E o corpo bate quase campo a campo com o que esta casa já guarda

```
cns
proclamas[]
   matricula · publicacao · livro_eletronico · data_proclamas
   tipo_casamento · cpf_fatura · nome_fatura
   conjuge_1 / conjuge_2
      cpf · nome · novo_nome · sexo · data_nascimento · estado_civil
      ocupacao · naturalidade_estrangeiro · ibge_municipio_naturalidade
      pais_nascimento · nacionalidade · domicilio_estrangeiro
      endereco_residencia { cep · logradouro · numero · complemento ·
                            bairro · ibge_municipio }
      filiacao[] { nome_genitor · sexo_genitor }
```

**`novo_nome` é o nome que cada cônjuge passa a usar** — o campo que este
projeto mediu em 28/08/2026 («o segundo cônjuge muda de nome em **17 dos 20**
casamentos») e que já está em `rc_pessoas`. **`ibge_municipio` de 7 dígitos** é
o mesmo código de `ib_municipios`, a tabela de 5.570 que a remessa do IBGE já
usa. **A filiação com `sexo_genitor`** é a que custou os 42 assentos com a mãe
no lugar do pai.

Ou seja: **o dado que a API pede já está quase todo dentro de casa.**

### As convenções, medidas na nota do contrato

| | |
|---|---|
| datas | `dd/mm/aaaa` |
| CPF | só dígitos, sem pontuação |
| CEP | `xxxxx-xxx` — **com** hífen |
| sexo | só `masculino` ou `feminino` |
| estado civil | `IGNORADO`, `SOLTEIRO`, `VIUVO`, `DIVORCIADO`, `SEPARADO`, `OUTROS` |
| tipo de casamento | `civil`, `religioso`, `conversao`, `afixacao` |
| país / nacionalidade | lista M49 da ONU (`076` = Brasil) |
| município | 7 dígitos do IBGE |

**O CPF vai sem pontuação e o CEP vai COM hífen, na mesma mensagem.** É o tipo
de detalhe que, escrito de memória, sai errado numa das duas.

---

## 2. A que ela não menciona no título — API DA CERTIDÃO ELETRÔNICA

**O contrato do e-Proclamas foi quem apontou para ela**, na nota de
autenticação: *«utilizará o **mesmo modelo de autenticação adotado no projeto
das certidões** (ON-RCPN)»*.

| | |
|---|---|
| contrato | `https://certidaoh.registrocivil.org.br/api/swagger.json` |
| documentação | `https://certidaoh.registrocivil.org.br/api/docs/index.html` |
| versão | **OpenAPI 3.0.0** · «API da Certidão Eletrônica 1.0.5» |
| segurança | `BearerAuth` — HTTP bearer, formato **JWT** |
| caminhos | **10** · 5 esquemas |
| substituiu as interfaces antigas em | **01/01/2025** |

```
POST /api/v1.0/obter-pedidos                    a FILA de pedidos
POST /api/v1.0/enviar-pedidos                   cumprir o pedido
POST /api/v1.0/rejeitar-pedidos                 recusar, com motivo escrito
POST /api/v1.0/certificate-json                 criar a certidão (dados)
POST /api/v1.0/certificate-file                 criar a certidão (PDF)
PUT  /api/v1.0/certificate-json/{id}            atualizar
PUT  /api/v1.0/certificate-file/{id}            atualizar
POST /api/v1.0/sign-certificate-json/{id}       assinar
GET  /api/v1.0/get-certificate-json/{id}        buscar o arquivo
POST /api/v1.0/cancel-certificate/{id}          cancelar
```

### E É AQUI QUE ESTÁ A AMPLIAÇÃO — sete módulos, e dois deles são REGISTRO

`obter-pedidos` recebe `{modulo, cns}`, e o contrato lista os módulos:

| código | o que chega por ele |
|---|---|
| `CRC` | pedidos de certidão no módulo do **Provimento 149** |
| `REG` | pedidos do site `registrocivil.org.br` |
| `JUD` | pedidos nos módulos **CRC-Jud** ou **Serp-Jud** |
| `EPR` | pedidos feitos na plataforma **e-Protocolo** |
| **`P13`** | **solicitações de REGISTRO DE NASCIMENTO nas Unidades Interligadas** |
| `RSE` | solicitações de certidão pelo módulo **«Registre-se»** |
| **`EOB`** | **solicitações de REGISTRO DE ÓBITO pelo módulo «e-Óbito»** |

**Cinco são pedidos de certidão; dois são pedidos de REGISTRO.** O `P13` traz o
nascimento pedido na maternidade — a Unidade Interligada, que o
`RCPN_O_QUE_FALTA_MEDIDO.md` já listava como coisa de fora que o RCPN depende —,
e o `EOB` traz o óbito pedido pelo e-Óbito.

**A resposta à pergunta do oficial é sim, e por larga margem.**

### As quatro espécies de certidão que ela monta

`certificate-json` recebe `{certidao, registro}`, e `registro` é **um de
quatro**:

| esquema | campos medidos |
|---|---|
| `Nascimento` | nome, CPF, matrícula, data e hora, naturalidade e nascimento (município/UF), sexo, **gêmeos**, filiação, **número da DNV**, averbação/anotação |
| `Casamento` | cônjuges, matrícula, data da celebração, **regime de bens**, averbação/anotação |
| `Obito` | nome, CPF, data e hora, local, sexo, estado civil, último cônjuge, idade, naturalidade, filiação, **causa da morte**, **nome e CRM do médico**, **local de sepultamento/cremação**, declarante, **existência de bens** |
| **`InteiroTeor`** | nome, CPF, matrícula, nome secundário, **texto da certidão** |

E `Certidao` traz `tipo_registro`, `tipo_certidao`, `transcricao`,
`cartorio_cns`, **`selo`**, `cod_selo`, `modalidade`, **`cota_emolumentos`** e
`cota_emolumentos_isento`.

### ISTO CRUZA COM DOIS ACHADOS QUE JÁ ESTÃO ABERTOS NESTE PROJETO

**O achado 2 do revisor registral** (31/08/2026) diz que *«causa da morte,
sepultamento e testamento não têm onde ser informados»* — as colunas existem em
`rc_assentos`, o termo sabe escrevê-las, e nenhum código as grava; **244 de 244
vazias**. **A Central pede exatamente esses campos** (`causa_morte`,
`nome_medico`, `crm_medico`, `local_sepultamento_cremacao`,
`existencia_bens`). Deixar de preenchê-los deixou de ser só descumprimento do
art. 80: passou a ser certidão que não sobe.

**O achado 3** diz que *«o civil não emite certidão de inteiro teor»* — **23 das
145** certidões reais desta casa. O esquema **`InteiroTeor`** está no contrato.

---

## 3. A autenticação é UMA SÓ para as duas — o IdRC

Medido na nota do contrato do e-Proclamas:

> «o **token de acesso (IdRC)** já utilizado para integração com o sistema de
> certidões **também poderá ser reutilizado** para autenticar requisições na API
> e-Proclamas, **sem necessidade de criação de um novo token ou credencial**.»

**O IdRC é o Sistema de Autenticação Eletrônica do Registro Civil**, e usa
**OAuth 2.0 e OpenID Connect** (página `onrcpn.org.br/icp-idrc/`). O token sai
do endpoint `/api/auth`, e o certidão declara `BearerAuth` com formato **JWT**.

**Como o cartório se cadastra**, literal do contrato:

> «Para acessar a API, é necessário ter um cadastro ativo. Acesse a página de
> **Solicitação de Cadastro** para iniciar o processo de registro»
> — `https://home.registrocivil.org.br/solicitacao-novo-client`

---

## 4. O QUE **NÃO** SE MEDIU, e por isso não se escreve

**1. O endereço de PRODUÇÃO.** Os dois contratos publicados são de
**homologação** — `servicos**h**.` e `certidao**h**.`. O endereço de produção
**não aparece em nenhum dos dois**, nem nos comunicados que se leu.

> **E é exatamente aqui que não se inventa.** Tirar o «h» do nome parece óbvio e
> **é palpite**: quem usasse um endereço adivinhado acharia que está testando
> enquanto fala com a Central de verdade, ou o contrário. É a mesma decisão da
> ONRTDPJ, onde o contrato declara **um** host e o sistema recusou inventar o
> segundo.

**2. O endpoint `/api/auth` e o corpo dele.** O contrato do e-Proclamas o cita e
**não o declara**; o do certidão declara `BearerAuth` e não diz onde se obtém o
token. Os dois apontam para o mesmo **manual num Google Docs**, que não está
nesta casa.

**3. Quais campos são obrigatórios.** Nos dois contratos, o e-Proclamas **não
declara `required` em nenhum parâmetro** e o certidão declara `required: []` nos
cinco esquemas — só os três corpos de fila (`obter`, `enviar`, `rejeitar`) têm
lista de obrigatórios. É a mesma situação dos `/v2` da CENPROT e do contrato da
ONRTDPJ, pela terceira vez: **não se inventa obrigação que o contrato não
declara**.

**4. O que a casa cobra.** `enviar-pedidos` exige `valor_emolumentos`,
`valor_adicional` e `quantidade_averbacao` — e as custas da certidão do RCPN
**estão medidas** neste projeto (`14.5.1` em 918 usos, `14.5.6` em 237,
`14.5.7` em 60). O que **não** está medido é a regra de
`quantidade_averbacao`, cuja descrição no contrato tem uma regra própria para
São Paulo.

---

## 5. O que isto significa para o sistema, sem decidir nada

O que já existe aqui e serviria de imediato:

| a Central pede | a casa já tem |
|---|---|
| os dois cônjuges com nome, CPF, sexo, estado civil, naturalidade | `rc_pessoas` — 264 pessoas entraram em 28/08 exatamente por isto |
| **`novo_nome`** | medido, e muda em 17 dos 20 casamentos |
| município IBGE de 7 dígitos | `ib_municipios`, 5.570 linhas |
| a filiação com sexo | `rc_pessoas`, com a régua do par que custou 42 assentos |
| o regime de bens | `rc_assentos.regime_bens` |
| a DNV | `strDeclaracaoNascidoVivo`, medida |
| o selo e a cota de emolumentos | `sd_selos` e `custas.py` |
| o teor do inteiro teor | é o achado 3, ainda aberto |

O que **falta**, e é do oficial:

1. **O cadastro em `home.registrocivil.org.br/solicitacao-novo-client`**, que
   gera o token IdRC — **um token para as duas APIs**.
2. **O endereço de produção**, que vem com o cadastro.
3. **O manual de autenticação** (o Google Docs citado nos dois contratos), que é
   o que fecha o `/api/auth`.

**Com essas três coisas, as duas integrações são o mesmo trabalho que a da
ONRTDPJ** — transporte medido contra o contrato guardado, tela, e testes que
abrem o `swagger.json` e comparam.

---

## 6. Uma observação de método

**Esta medição só aconteceu porque o oficial mandou procurar.** Horas antes,
neste mesmo dia, eu havia escrito que sobre a Central do RTDPJ «não havia
contrato a medir» — e o contrato estava público. **A lição vale duas vezes no
mesmo dia**: o e-Proclamas está no `CLAUDE.md` desde 28/08/2026 como *«integração
que este sistema ainda não tem»*, e a API existe desde **10/04/2025**.

**Não achar onde eu procurei não prova que não existe.** E, das duas vezes, quem
mandou procurar noutro lugar foi ele.

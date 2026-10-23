# O ONR — o item 3 do cronograma

> «siga no desenvolvimento das integrações até terminar de todas, sem minha
> intervenção» — o oficial, 03/09/2026.

O maior contrato das quatro: **39 caminhos, 53 operações, 73 esquemas**.

---

## 1. O que passou a existir

| | |
|---|---|
| `onr_api.py` | o transporte — **13 das 53 operações**, e as 53 declaradas |
| `ri_onr_central_schema.py` | `ri_onr_envios` — o rastro do que sobe |
| `ri_onr_central.py` | o indicador real, o edital do usucapião e a fila |
| `ri_onr_web.py` | nove rotas, em **Registro de Imóveis → ONR** |
| `tools/gerar_logradouros.py` | gera os três vocabulários do contrato |
| `templates/ri_onr_central.html` · `ri_onr_indicador.html` · `ri_onr_edital.html` | as telas |

---

## 2. Antes de tudo: eu escrevi por cima de um módulo que existia

**`ri_onr.py` já era um módulo desta casa**, e eu lhe dei esse nome sem
conferir. Ele gera os **arquivos** do ONR — o Indicador Pessoal em XML
(`BANCOLIGHT`) e o Indicador Real em JSON —, e o formato dele **foi levantado
dos arquivos que esta serventia realmente enviou**, em `C:\ARPNET\C11\ONR`.
`ri_web.py` importa dele quatro nomes.

**Quem avisou foi o `ImportError` ao carregar o `app`**, e não a releitura. O
original voltou do `.cgu` da 3.6.65, e a restauração foi **conferida por
hash**: `ri_onr.py`, `templates/ri_onr.html` e `ri_web.py` estão **byte a byte
iguais** ao pacote — nada se perdeu. O meu passou a se chamar
`ri_onr_central.py`, que é o que ele é: a **API** da Central.

**A regra que fica:** antes de criar arquivo, veja se o nome está livre. A
ferramenta diz «atualizado» em vez de «criado» quando não está, e eu não li.

### E o engano revelou o achado que mais importa

**As duas tabelas de tipo de imóvel são diferentes:**

| | códigos |
|---|---|
| `ri_onr.TIPO_IMOVEL_ONR` — o **arquivo** | **0 a 9**, do `tbRI_TipoImovel.onr_id` do E-Ofício |
| `onr_api.TIPOS_DE_IMOVEL` — a **API** | **64** = Casa, **65** = Apto, **15** = Loja, **71** = Terreno/Fração… |

Usar uma pela outra poria «Loja» onde é «Casa» **no índice que o país consulta
para saber de quem é o imóvel**. Há teste que exige que as duas não tenham um
único código em comum, e que fica vermelho no dia em que tiverem.

---

## 3. As armadilhas medidas do contrato

### 3.1. O `openapi.json` que eles publicam não é JSON válido

Duas vírgulas antes de fecho (`,}`) — qualquer parser recusa o arquivo inteiro.
Por isso há **duas cópias**: a original, que prova o defeito, e a limpa, que os
testes leem. E o teste que as compara **não compara bytes**:

> **A primeira versão dele comparava tamanho**, e passaria ou falharia por
> acaso — a cópia limpa foi reserializada com outra indentação, e difere em
> **86.507 bytes** sem que o conteúdo mude. Ele agora tira a vírgula do
> original e compara os **objetos**. Comparar a forma onde o que importa é o
> conteúdo mede a coisa errada.

### 3.2. Os dois ambientes vêm do contrato

`servers` traz `api.` e `testes-api.`. **É o oposto do ON-RCPN**, que só
publica os de homologação — e por isso aqui não se adivinha endereço nenhum. A
casa começa na de testes.

### 3.3. A autenticação é um par, e está medida

`POST /v1/auth/token`, corpo **`x-www-form-urlencoded`** (e não JSON), com
`client_id`, `client_secret` e `grant_type=client_credentials`. Volta
`{access_token, expires_in, token_type: "Bearer"}`.

**É por isso que o ONR entrou em `centrais_cred` como `PAR` e a ON-RCPN
continua `TOKEN`:** lá o cadastro também devolve um par, e o endereço que o
troca por token **não está medido** — os dois contratos citam um `/api/auth`
que responde 404 nos dois hosts da API.

**O token se guarda na memória; o segredo, não.** `expires_in` manda: guardar
«para sempre» faria a casa mandar token vencido sem saber, e pedir a cada
chamada seria uma viagem a mais por clique. **Sem `expires_in` não se guarda.**
E **trocar a credencial joga o token fora** — sem isso, quem corrigisse o
`client_secret` continuaria falando pelo token velho e concluiria que a
correção não pegou.

### 3.4. São dois mecanismos de autenticação na mesma API

| | |
|---|---|
| `bearerAuth` | **48** operações — `Authorization: Bearer <token da serventia>` |
| `headerAuth` | **4** operações — cabeçalho `token: <token DAQUELE protocolo>` |

As quatro são os **detalhes do protocolo**, e o token delas sai de
`POST /v1/protocolo/{n}/token`. Mandar o `Bearer` ali devolve 401 sem dizer por
quê.

### 3.5. Três caminhos não declaram segurança

Um é o `/v1/auth/token`, e está certo. Os outros dois são
`POST /v1/edital/cobranca` e `PATCH /v1/edital/cobranca/{numeroDocumento}` —
mesma Central, mesma credencial. **É omissão do contrato**, e há teste que fica
vermelho quando corrigirem.

### 3.6. O `oauth2` declarado aponta para lugar nenhum

`"tokenUrl": "https://teste/oauth2/token"` — endereço que não existe. Sobra de
configuração deles.

### 3.7. O enum deste contrato é documentação, e não valor

Os campos de código são `type: integer` e trazem
`enum: ["64 = Casa", "65 = Apto", …]` — **strings com o número, o igual e o
nome**. Quem mandar a string manda texto onde a Central espera número.

`codigos_do_enum` parte a lista, e é dela que `tools/gerar_logradouros.py` gera
os três vocabulários **transcritos** para dentro de `onr_api.py`:

| | |
|---|---|
| tipos de logradouro | **129** |
| tipos de ato | **23** |
| tipos de imóvel | **10** |

Eles são transcritos, e não lidos em tempo de execução, porque o contrato mora
em `FONTES_EXTERNAS`, que **não viaja no `.cgu`** — a decisão de
`atribuicoes.py`, que é «gerado do acervo». Há teste que compara os três com o
contrato.

> **E a primeira versão do gerador partiu nomes no meio.** Ele usou
> `textwrap.wrap` e produziu `'Praça de\nEsportes'` — um arquivo que nem
> compilava, com vinte e cinco erros de sintaxe. **Texto que contém espaço não
> se quebra por largura.**

### 3.8. Um nome aparece duas vezes no catálogo deles

«Alameda» é **4 e 645**. Medido, e não suposto. Para o caminho contrário — do
nome para o código — fica o **menor**, que é o da sequência, e a duplicata fica
declarada em `NOMES_REPETIDOS_NO_CATALOGO`.

### 3.9. `tipoLogradouro` é `integer` num lado e `string` no outro

No `indicadorRealRequest` é o **código**; no `editalRequest` é o **nome**
(`string max=16`). Mesmo nome de campo, dois tipos, no mesmo documento — e é
por isso que a tabela dos 129 serve aos dois lados.

### 3.10. A localização pula o 2

`1 = Urbano`, `3 = Rural`. Catálogo oficial pula número — a lição dos catálogos
do IBGE. Quem preencher a sequência óbvia acerta o tipo e erra o conteúdo.

---

## 4. Enviar não é ser aceito

O ONR **recebe e processa depois**, numa fila própria
(`/v1/fila/processamento/protocolo`). Por isso `ENVIADO` e `ACEITO` são duas
situações, e há um botão que pergunta a ele o que aconteceu.

**E o que a fila diz só muda a situação quando a palavra é conhecida.** Chutar
«aceito» sobre uma palavra que não se conhece faria a casa dar por publicado o
que o ONR recusou — o defeito do e-Proclamas noutra forma.

---

## 5. O que a casa manda, e o que ela recusa mandar

### 5.1. Onze dos doze obrigatórios saem da ficha

O décimo segundo é `situacaoConstrucao`, e **esta casa não o guarda em coluna
nenhuma** — medido nas 50 colunas de `ri_matriculas`. Ele vai como **«Não se
aplica»**, que é o menos afirmativo dos três, **e a tela diz isso** com a caixa
para trocar. Deixá-lo em branco não dava: o contrato o declara obrigatório. E
exigir a escolha em cada uma das 1.701 matrículas produziria uma tela que
ninguém usaria.

**E o zero é resposta:** «Construção Averbada» é o código **0**, e o filtro de
vazios o tiraria. Há teste.

### 5.2. Só o dono de hoje vai

`proprietario_ativo`, e não `proprietario`. A segunda diz que a pessoa já foi
dona; a primeira diz que ela é. Mandar as duas **publicaria como proprietário
quem vendeu**.

### 5.3. O ato que não casa não some calado

A natureza do título é campo livre; o ONR tem 23 códigos. O que casa vai, e **o
que não casa aparece na tela com o número do ato** — sumir com ele faria o
índice mostrar uma cadeia com buraco.

### 5.4. O registro anterior não se reparte

O ONR o quer em número, tipo e CNS; a casa guarda **texto**. Repartir por conta
própria poria o número de um livro no lugar do outro. **Ele não vai, e a tela
diz.**

### 5.5. O tipo do imóvel não casa por semelhança

«Barracão de zinco» **não vira** «Galpão». A conferência impede e lista os dez
que o ONR aceita.

### 5.6. O acervo não vira atraso

As 1.270 fichas `ACERVO` **não entram** na lista do que falta subir: elas
vieram de um sistema que já respondia ao ONR, e mandá-las encheria a fila deles
com o que já está lá. **E o `RECUSADO` volta para a lista** — recusado é
trabalho a refazer, e não trabalho feito.

---

## 6. O edital: o sistema já calculava o prazo e não tinha como disponibilizar

O art. 755, § 1º do Código de Normas do TJMA conta a publicação a partir do
**primeiro dia útil depois da disponibilização na Central**. O sistema calcula
esse prazo desde 28/08/2026 — **e não tinha como disponibilizar nada**.
`POST /v1/edital` é a disponibilização.

**A lista dos tipos de edital não se escreve no código**: ela vem da própria
Central (`/v1/edital/tipo`). Escrevê-la aqui seria a lista à mão que envelhece
na tarde em que se escreve.

**E o edital não sobe enquanto os intimados não tiverem documento.** O ONR o
declara obrigatório em cada um, e `us_movimentos` **não tem coluna de
documento** — só nome e endereço. Enquanto ela não existir, a tela diz isso em
vez de inventar número.

---

## 7. Corrigir não queima o identificador

Excluir e mandar de novo daria um `hash` novo, e quem consultou o índice
ficaria com um número que não aponta para nada. O botão «Corrigir no ONR»
reenvia e **mantém o identificador** — a mesma razão do «Corrigir na Central»
da certidão eletrônica.

> **O varredor de função órfã achou nove.** Quatro ganharam tela
> (`esquecer_o_token`, `atualizar_indicador`, `detalhes_da_fila`,
> `indicadores`), **quatro foram apagadas** — `atos_do_indicador`,
> `excluir_indicador`, `retificar_edital`, `detalhes_do_protocolo`, escritas
> «para o caso de» — e uma foi **declarada**: `codigos_do_enum` é a régua que o
> teste usa para comparar o vocabulário com o contrato, e tela ela não deve ter.
>
> **Os caminhos das apagadas continuam declarados em `CAMINHO`**, para ninguém
> os reinventar — a decisão do `renegociacoes()` da CENPROT.

---

## 8. O que rodou

| | |
|---|---|
| `tests/test_onr_api.py` | **38** — todos abrem o contrato e comparam |
| `tests/test_ri_onr_central.py` | **35** — o domínio e as telas, sem rede |
| varredores (função órfã · CSRF · débitos do balcão · portabilidade · menu · esquemas) | verdes |
| a fatia do RI inteira | **170** |
| `ruff check` nos módulos novos | limpo |

**Nenhum teste fala com o ONR.**

---

## 9. O que depende do oficial

1. **A credencial do ONR** — um **par**, `client_id` + `client secret`. Ela se
   pede ao ONR, e o sistema começa na de **testes**, que o contrato declara.
2. **A coluna de documento dos intimados** do usucapião, sem a qual o edital
   não sobe.
3. **Conferir a situação da construção** nas matrículas em que ela importe — o
   sistema manda «Não se aplica» e diz que manda.

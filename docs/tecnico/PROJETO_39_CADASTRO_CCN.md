# Projeto — relatos #39 e #38

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000
Relatos internos #39 e #38 · 31/08/2026 · versão 3.6.51 · oficial
Este arquivo é o projeto. A fatia 1 (domínio) já está no código; webcam, leitor e CCN ainda não.

Dois problemas, um projeto. O #39 é o cadastro (foto, digital, CCN). O #38 é o termo do registro civil (nascer, casar, morrer) — a página que veio vazia.

---

## O que o oficial pediu

Na abertura da ficha de firma: tirar foto pela webcam, colher digital no aparelho de biometria, e ter ferramenta para mandar as fichas ao Cadastro de Clientes do Notariado.

## O que isto NÃO é

**A ficha de firma não muda.** Decisão do oficial em 31/08/2026, neste chat. O papel que se imprime, se assina e se guarda continua o de hoje (`/notas/cartoes/<id>/ficha`, o `.odt` com espaço marcado para foto e digital). Quem confere por semelhança no balcão não ganha layout novo.

O relato #8 já tinha feito essa ficha imprimir, e deixado foto e digital de fora de propósito: das 436 biometrias do acervo, só 2 eram legíveis, e o oficial decidiu colher novas. Este projeto é a continuação daquele — a parte que ficou de fora.

## O que muda

O **cadastro da pessoa** como um todo. Em Notas **não há tabela `pessoas` nem `clientes`**: o cadastro *é* o cartão de autógrafo (`nt_cartoes`). `rc_pessoas` é gente do assento de RCPN, outro domínio. É em `nt_cartoes` que entram:

1. a fotografia colhida no balcão
2. as digitais colhidas no leitor
3. o envio desse cadastro (com a ficha) ao CCN

A abertura da ficha é só o momento: a pessoa está presente, a webcam e o leitor estão na mesa. O dado não mora na ficha; mora no cadastro, e a ficha pode continuar mostrando o espaço em branco no papel até a foto/digital existirem — ou passar a puxá-las do cadastro na hora de imprimir, sem mudar o desenho.

Se no futuro o cadastro de pessoas se unificar entre atribuições, foto e digital viajam com a pessoa. Não ficam presas ao layout do cartão.

---

## Para onde isso vai: o CCN

O destino não é um arquivo solto. É o **Cadastro Único de Clientes do Notariado** da plataforma e-Notariado (CNB-CF), base nacional prevista no Provimento CNJ nº 149/2023.

Documentação usada neste projeto (não inventar campo fora disto):

- Técnica: https://suporte.notariado.org.br/support/solutions/articles/43000585342-ccn-documentacao-tecnica
- Esclarecimentos: https://suporte.notariado.org.br/support/solutions/articles/43000595164-ccn-esclarecimentos-gerais
- Chaves: https://suporte.notariado.org.br/support/solutions/articles/43000589284-ccn-geracao-das-chaves-de-integracao
- Dispositivos: https://suporte.notariado.org.br/support/solutions/articles/43000605934-dispositivos-biometricos-modelos-homologados
- API: https://pessoas.e-notariado.org.br/swagger/index.html
- Homologação: https://pessoas-hml.e-notariado.org.br · Produção: https://pessoas.e-notariado.org.br

**Nome que confunde.** O oficial disse «exportar para o CCN». No vocabulário do CNB, mandar o cadastro *deste* sistema *para* o CCN é **Importar**. «Exportar», no CCN, é o contrário: consultar o CCN a partir daqui. Este projeto faz o envio (Importar). Consultar o CCN por CPF fica para um passo seguinte, se o oficial quiser.

Quem deve ir: toda pessoa com firma aberta, e as qualificações dos atos notariais. Periodicidade máxima: 15 dias (art. 166 § 1º do Prov. 149/2023). Carga desde 01/10/2019, se possível. Transmitir o cadastro, sem credenciar Autoridade Notarial, **não tem custo**.

CPF e nome são o mínimo que o CCN aceita. O resto (foto, digital, ficha, RG, endereço) vai o que a casa tiver. Foto colhida no balcão leva `fotoVerificada=true`.

Dedos no domínio do CCN: 1–10 (polegar direito até mínimo esquerdo). Biometria, se enviada, obriga dedo + imagem juntos (png, jpg ou pdf em Base64). Ficha: data, número, imagem (png, jpg, pdf ou tiff).

---

## Três peças, nesta ordem

### 1. O cadastro guarda foto e digital

Novo módulo de domínio (`cadastro_biometria.py`), com `con` recebido. A rota só liga os fios.

**O que o banco já tem, medido em 31/08/2026 no `cartorio_gestao.sqlite3`:** 4.062 cartões (4.060 do E-Ofício, 2 manuais); 2.956 com autógrafo digitalizado e **1.106 sem**; colunas `biometria` (texto, molde do leitor antigo) e `biometria_dedo` (inteiro). Há **462** moldes velhos e **zero** com o dedo marcado — a importação lia o campo errado (`notas_import.py`). Esses 462 não são imagem, não servem ao CCN, e **não se reaproveitam**. A coluna de texto fica como legado; a coleta nova grava **imagem** no disco.

No disco, não no SQLite, iguais às fichas de hoje (`nt_cartao_imagens`, pasta `%PROGRAMDATA%\CartorioGestao\arquivos\notas\firmas\{id}\`). Foto de rosto e as quatro digitais são arquivos novos (JPEG/PNG), com caminho, espécie, qual dedo (1, 2, 6, 7), quando, quem colheu, e se a foto foi presencial. `ajuda_privacidade` já trata `biometria` como dado sensível — a foto e as digitais novas entram na mesma barreira.

Na tela de cadastro do cartão (`/notas/cartoes/<id>` e no formulário de abertura):

- **Foto:** a webcam do navegador (`getUserMedia`). Chrome no balcão. Sem programa extra. Recorte de rosto, uma foto, JPEG. Dá para refazer. Webcam não tem lista homologada; o CNB só sugere Full HD. Qualquer webcam do balcão serve.
- **Digital:** o navegador **não fala com o leitor USB** sozinho. Precisa de um ajudante local na máquina do balcão — e desde 26/10/2026 esse ajudante é o **do fabricante**: o cliente HID DigitalPersona, com o SDK web dele carregado na tela (ver «Fatia 2b — o leitor no navegador», abaixo). Sem o cliente ou sem o SDK, a tela diz qual faltou e o envio manual da imagem continua.

GET não grava. Colher é POST. Erro de regra (leitor ausente, captura vazia, dedo repetido) é `ValueError` em português, dizendo o que fazer. Relatório de problema e auditoria **não levam a imagem** — só o fato de ter colhido.

A ficha impressa não é redesenhada. Se a foto/digital existirem no cadastro, o `.odt` pode preenchê-las no espaço que já está marcado. Se não existirem, o espaço continua em branco, como hoje.

Abrir o cartão e selar **não espera** CCN nem leitor. A pessoa pode ser cadastrada agora e colher biometria no próximo comparecimento. Fila visível: cadastros sem foto, sem digital, sem envio.

### 2. Montar o XML do CCN e enviar

Módulo próprio (`ccn.py`), também com `con`. Monta o XML no XSD do CNB (v4). Sobe por API: `POST /api/uploads` (multipart, `contentType=text/xml`) e `POST /api/imports` (`type: CcnPessoaFisica`), headers `X-Api-Key` e `X-Subscription`. Acompanha `GET /api/imports/{id}` e lê `/errors`.

Chaves moram em credencial da casa, no mesmo lugar de `selador.cred` / `claude.cred` — **nunca** no código, nunca no relatório de problema.

Um cadastro por vez na abertura (a pessoa acabou de ser colhida). Lote à parte para o acervo antigo, fora do horário de balcão, arquivo < 30.000 KB. CCN fora do ar não trava o balcão: o envio fica pendente, com recado em português.

O CNB pede acordo de cooperação técnica com o fornecedor do software. Esta casa *é* o fornecedor. O oficial preenche o formulário do CNB em nome da serventia, pede homologação e chave para `servicos@cnbcf.org.br`.

Consultar o CCN (a «exportação» do CNB, com certificado ICP-Brasil) **não entra neste projeto**.

### 3. O acervo que já existe

4.062 cartões. Os 462 moldes de `nt_cartoes.biometria` não se reaproveitam (relato #8: só 2/436 legíveis, e mesmo esses são template, não imagem). Foto e as quatro digitais novas se colhem quando a pessoa voltar. Os 1.106 cartões sem autógrafo digitalizado também entram na fila do que falta.

O lote ao CCN pode sair antes, só com CPF, nome e a ficha que já temos nos outros 2.956 — o CCN aceita cadastro incompleto. Não se manda molde velho. Não se inventa foto.

---

## O que o oficial ainda decide

Os quatro pontos que travavam implementação estão decididos. 31/08/2026.

1. **Onde colher a digital.** DECIDIDO em 31/08/2026: neste sistema, depois mandar ao CCN. Não colher no site do CCN. Sem licença por estação.
2. **Qual leitor.** DECIDIDO em 31/08/2026: DigitalPersona U.are.U 4500 ou 4000b, homologado pelo CNB. Driver/SDK DigitalPersona. O ajudante local da máquina do balcão fala com esse aparelho.
3. **Quantos dedos.** DECIDIDO em 31/08/2026: os quatro de identificação — polegar direito, indicador direito, polegar esquerdo, indicador esquerdo (códigos CCN 1, 2, 6, 7).
4. **Obrigatoriedade na abertura.** DECIDIDO em 31/08/2026: foto e digital NÃO são obrigatórias para abrir firma. Podem ficar para a próxima visita. O cadastro avisa o que falta. O selo de abertura não espera webcam nem leitor.

---

## Regras da casa que este projeto não fura

- Módulo de domínio primeiro; rota só liga.
- `MIGRACOES` só `ALTER TABLE ADD COLUMN`. Tabela nova vai no `SCHEMA`. Índice de coluna nova em `INDICES_DEPOIS_DA_MIGRACAO`.
- `audit()` fora de `db.transaction()`. `q` / `q1` fora de transação.
- GET não escreve.
- Imagem no disco, caminho no banco.
- Dado pessoal não sai em relatório de problema.
- Teste sem aparelho: JPEG e PNG de fixture, XML conferido contra o XSD, API do CCN em dublê. O teste que precisa de leitor de verdade não roda no lote — fica marcado.
- CCN fora do ar é recado, não HTTP 500 na cara do escrevente.

---

## Prova de que está feito

Quando isto existir, a nota de desenvolvimento do #39 aponta:

- abrir um cadastro de teste, colher foto pela webcam, colher as digitais do leitor, ver os dois no cadastro e **a ficha impressa igual à de hoje**, só com o espaço preenchido se houver imagem
- gerar o XML de uma pessoa conhecida e conferir no validador do XSD v4
- enviar à homologação (`pessoas-hml`) e ver o import `Successful`
- um cadastro sem foto/digital continua abrindo, selando, e aparece na fila do que falta

Este arquivo mora em `docs/tecnico/PROJETO_39_CADASTRO_CCN.md`.

---

## Parte 2 — relato #38: o termo tem que sair usável

Relato #38 · aberto 31/08/2026 17:23 · `/rcpn/244` · versão 3.6.51 · oficial · ABERTO

**Título:** tentei gerar um termo de óbito e a página não tinha nenhuma informação.

**O que fazer, nas palavras do oficial:** revisar a estrutura dos termos de nascimento, óbito e casamento; retirar a explicação de por que tem três colunas; deixar usável.

### O que aconteceu

Ele foi no assento `/rcpn/244` gerar o termo de óbito e a tela veio sem o termo. O detalhe não pede um conserto só daquele assento: pede a estrutura dos **três** termos (nascimento, casamento, óbito).

A página vazia tem causa medida. O E-Ofício não guardava o teor — montava na hora de imprimir. A carga trouxe 244 assentos com `rc_assentos.teor` vazio. A folha (`/rcpn/<id>/folha`) **não monta** o texto: só imprime o que já está gravado. Ordem de 30/08: no assento importado o termo existe em papel, e o sistema tem as informações. Resultado, na prática: clicar em gerar mostra a geometria das três colunas e uma aula sobre a inspeção da COGEX — e o termo, que é o que se veio buscar, não aparece.

### O que isto NÃO é

**As três colunas não saem do papel.** Elas são exigência da Inspeção Ordinária de 12/08/2026 (COGEX), págs. 49–50, livros A-24, B-04, C-05 e D-03: campo próprio para notas, averbações e retificações, inclusive no verso. Medidas no termo de nascimento nº 8.369 desta casa (paisagem, ~10% / ~62% / ~28%). Isso mora em `rc_folha.py` e continua.

O que sai é a **explicação** na cara de quem vai lavrar. Quem gera um termo não precisa ler de novo por que a folha tem três colunas. Precisa do termo preenchido, pronto para conferir e imprimir.

A ficha de firma do #39 continua sem mudar. Este pedaço é só RCPN.

### O que muda

1. **Gerar o termo mostra o texto**, montado dos dados do assento (`rc_termo.montar` / modelos do livro, opção B de 31/08: o catálogo da casa, não os treze do E-Ofício). Página sem informação é defeito, não geometria.
2. **Nascer, casar e morrer usam a mesma estrutura de tela.** Cada espécie tem o modelo certo (nascimento já reconstruído dos requisitos; óbito dos doze incisos do art. 255; casamento no mesmo critério). A tela é uma, o corpo muda.
3. **A aula das três colunas sai da tela de uso.** A geometria fica no papel e na documentação do programador. No balcão: número, termo, margem — usável.
4. **Assento antigo sem `teor`.** Gerar **mostra** o termo montado dos campos. Não grava por cima sem o oficial confirmar — o papel do livro antigo continua sendo a fonte do que já foi lavrado. Assento novo congela uma vez, como hoje (`rc_termo.congelar`).
5. Campos em branco no cadastro aparecem como lacuna visível no termo («o que falta»), não como página vazia inteira.

### Prova de que o #38 está feito

- abrir `/rcpn/244` (e um nascimento e um casamento) e gerar o termo: o texto aparece, com os dados do assento
- a tela não traz parágrafo explicando as três colunas
- a folha impressa segue paisagem, três colunas, frente e verso
- um assento importado sem `teor` não grava termo novo só porque alguém abriu a pré-via
- teste sem dado pessoal: fixture com os três espécies, teor vazio e teor já congelado

---

## Parte código — o corte maduro

Isto é o projeto de código. Ainda não é o atualizador. Nada disto sobe com `ATUALIZAR_SISTEMA.cmd` até os testes do lote passarem nesta pasta.

A ordem não é gosto: cada fatia é usável sozinha no balcão, e a seguinte não depende de hardware que ainda não está no ar.

### Fatia 1 — o cadastro guarda foto e digital (domínio)

Arquivos:

| arquivo | o que faz |
|---|---|
| `cadastro_biometria.py` | domínio: colher, substituir, estado, listar. `con` recebido. |
| `notas_schema.py` | tabela nova `nt_cadastro_imagens` no `SCHEMA` |
| `tests/test_cadastro_biometria.py` | sem aparelho: JPEG/PNG de fixture |
| `ajuda_privacidade.py` | foto e digital novas na mesma barreira de `biometria` |

Tabela `nt_cadastro_imagens` (CREATE TABLE IF NOT EXISTS, não é MIGRACAO):

- `id`, `cartao_id` (FK `nt_cartoes`)
- `especie` `FOTO` \| `DIGITAL`
- `dedo` NULL na foto; 1, 2, 6 ou 7 na digital
- `caminho`, `nome_arquivo`, `sha256`, `bytes`
- `presencial` (1 = `fotoVerificada` no CCN)
- `colhido_em`, `colhido_por`
- `UNIQUE(cartao_id, especie, dedo)`

Disco: `%PROGRAMDATA%\CartorioGestao\arquivos\notas\firmas\{cartao_id}\foto.jpg` e `digital_{dedo}.png`. O banco não leva o blob.

Funções: `colher_foto`, `colher_digital`, `estado`, `imagens_do_cadastro`. Dedo fora de `{1,2,6,7}` ou bytes vazios → `CadastroBioError` em português, dizendo o que fazer. Recolher substitui arquivo e linha. `estado().faltando` lista o que falta; **não impede** abrir nem selar.

**Não fazer nesta fatia:** webcam na tela, ajudante USB, XML CCN, mexer no `.odt`, `ATUALIZAR_SISTEMA`.

**Não reusar** `nt_cartoes.biometria` / `biometria_dedo`. São molde do E-Ofício, 462 linhas, zero com dedo. Legado.

### O que já está no código

Fatia 1, 31/08/2026 — domínio, sem webcam, sem leitor, sem envio ao CCN:

| arquivo | o que faz |
|---|---|
| `cadastro_biometria.py` | `colher_foto`, `colher_digital`, `estado`, `imagens_do_cadastro`. `con` recebido. |
| `notas_schema.py` | tabela `nt_cadastro_imagens` no `SCHEMA`, com índices parciais (uma foto e uma imagem por dedo; UNIQUE de tabela não trava duas FOTO com `dedo` NULL no SQLite). |
| `tests/test_cadastro_biometria.py` | sem aparelho: JPEG/PNG de fixture; blob não entra no SQLite. |
| `ajuda_privacidade.py` | `fotografia`, impressão digital e `foto.jpg` / `digital_N.png` na mesma barreira de `biometria`. |
| `notas_web.py` + `templates/notas_cartao.html` | GET `/notas/cartoes/<id>` mostra `estado().faltando`. Só leitura. |

### Fatia 2 — a tela do cadastro colhe (sem CCN)

| arquivo | o que faz |
|---|---|
| `templates/notas_cartao.html` | bloco «Foto e digitais» no cadastro, não na ficha impressa |
| `static/cadastro_captura.js` | `getUserMedia` (foto); POST da digital via ajudante |
| `notas_web.py` | POST `/notas/cartoes/<id>/foto` e `/digital`; GET só lê `estado` |
| ajudante Windows (fatia 2b) | o cliente do fabricante (HID DigitalPersona) + o SDK web dele — ver abaixo |

GET não grava. Sem leitor, a foto ainda funciona; a digital recusa em português («ligue o leitor DigitalPersona e tente de novo»).

O `.odt` da ficha **não muda o desenho**. Se o cadastro tiver foto/digital, preenche os quadros que já existem; se não tiver, ficam em branco.

### Fatia 2b — o leitor no navegador (26/10/2026)

Decisão do oficial: integrar o leitor da casa, do padrão do e-Notariado, que ele chamou de «DigitalPersona U 7500». **O nome comercial exato não se confirmou**: na máquina de desenvolvimento não há driver, serviço nem programa da HID (medido com `Get-PnpDevice`, `Get-Service` e as pastas de programas, só leitura); a decisão de 31/08 fala em U.are.U 4500/4000b. A tela diz «HID DigitalPersona (família U.are.U)» até alguém conferir a etiqueta do aparelho.

**O caminho escolhido é o SDK web do fabricante, no próprio navegador**, e não um serviço local nosso no modelo do `a3_servico_local.py`:

- o fabricante instala no Windows do balcão o cliente dele («HID DigitalPersona Lite Client» / «Authentication Device Client»), que fala com o aparelho e abre um canal só em 127.0.0.1 para o navegador. É o ajudante local que esta fatia pedia, e é o que o e-Notariado já exige no balcão — não se instala um segundo programa para o mesmo aparelho;
- a DLL nativa do SDK carregada por processo nosso é o risco que o A3 já mostrou nesta casa (segfault derruba o processo); no navegador, se o cliente cair, cai a captura e não o servidor;
- nenhuma porta nova nossa para vigiar.

| arquivo | o que faz |
|---|---|
| `leitor_digital.py` | o nome do leitor, a **finalidade** (LGPD art. 11), a pasta do SDK, a lista fechada dos dois arquivos do SDK, `e_png` |
| `static/leitor_digital.js` | usa `Fingerprint.WebApi`: procura o leitor, mostra o estado (sem SDK / cliente não respondeu / leitor não conectado / conectado), pede **PNG** do dedo escolhido e manda pelo formulário escondido com `origem=LEITOR` |
| `notas_web.py` | `GET /notas/leitor-digital/sdk/<nome>` serve os dois arquivos do fabricante, só da lista; o POST `/notas/cartoes/<id>/digital` é **o mesmo** do envio manual e grava `origem` e `dispositivo` |
| `cadastro_biometria.py` | `colher_digital(..., origem, dispositivo)`: do leitor, só PNG; o aparelho só se grava quando a imagem veio dele |
| `notas_schema.py` | `nt_cadastro_imagens.origem` (LEITOR ou ARQUIVO) e `.dispositivo` — migração |
| `tests/test_leitor_digital.py` | sem aparelho: o retorno do leitor **simulado** pelo formulário que o JS manda |

**Os arquivos do SDK não estão no repositório**: são do fabricante. O TI copia `websdk.client.bundle.min.js` e `fingerprint.sdk.min.js` (os da amostra JavaScript do pacote do SDK) para `<pasta de dados>\terceiros\digitalpersona` — ou para a pasta da configuração `leitor_digital_sdk_pasta` — e instala o cliente HID DigitalPersona em cada computador do balcão. Sem os dois arquivos, a tela diz o que falta e onde pôr.

**Template ISO/ANSI (FMD): o SDK web não entrega.** Os formatos dele são imagem crua, WSQ, PNG e o «intermediário» proprietário da DigitalPersona. Guarda-se o PNG, com sha256, no disco; **o intermediário não se colhe** — dado biométrico se colhe no mínimo que a finalidade pede (LGPD art. 6º, III), e um formato que só o fabricante lê não serve ao CCN.

**Finalidade (LGPD, art. 11)** — o texto que a tela mostra acima dos dedos, de `leitor_digital.FINALIDADE`: as digitais servem para identificar quem abre a ficha de firma e quem volta para reconhecer firma, e para compor o CCN. Dado biométrico é dado pessoal sensível: fica só no cadastro desta serventia, não vai para relatório, auditoria, log nem para a ajuda. A auditoria leva **dedo e origem**, nunca a imagem; o JavaScript não escreve nada no console nem no armazenamento do navegador. **A hipótese legal do art. 11 que sustenta a coleta é decisão do oficial** e está A CONFERIR.

**Correções de segurança de 26/10/2026 (revisão do PR #31) — e os limites que ficam declarados:**

- **A origem «do leitor» é declarada pelo navegador, e não provada.** É um campo do formulário: quem o edita manda um PNG qualquer como «do leitor». Sem canal assinado com o cliente do fabricante não há prova possível. O servidor recusa `LEITOR` quando o SDK nem está instalado nele (`leitor_digital.recusa_da_origem`), a auditoria grava `origem_declarada_pelo_navegador`, e a tela diz «informada como do leitor», e não «do leitor» como fato.
- **A ciência do titular fica registrada no cartão** (`nt_cartoes.biometria_ciencia_em` / `_por`), com a caixa «Li para a pessoa a finalidade acima, e ela concordou…» e a auditoria `NT_CADASTRO_BIOMETRIA_CIENCIA`. **Sem ela nenhuma digital se colhe** — nem do leitor, nem de arquivo. A hipótese legal continua A CONFERIR pelo oficial (`leitor_digital.BASE_LEGAL`); até ele decidir, vale a mais fechada: trata-se como consentimento (art. 11, I).
- **A imagem da digital não é mais servida ao AUDITOR**: a ficha dele diz «digital colhida em <data>», sem a imagem. Cada vez que a imagem sai para a tela, a auditoria anota `NT_CADASTRO_DIGITAL_VISTA` (o dedo, nunca a imagem).
- **A imagem continua EM CLARO no disco** (`notas\firmas\<cartão>\digital_<dedo>.png`), na pasta de arquivos que o backup varre. Cifrá-la com a chave do cofre não foi feito, e é decisão do oficial: a `cofre.key` mora na pasta de dados e, perdida (máquina nova, restauração), **as digitais não abrem mais** — o contrário do «perder a chave não tranca nada» do cofre —, e o envio ao CCN (`ccn_envio`) teria de decifrar. Enquanto isso, o que protege a cópia externa é **ligar a cifra do backup** (`backup.cred`, AES-256-GCM).
- **O canal do cliente HID em 127.0.0.1 não tem trava de origem da casa**, porque o canal não é nosso: qualquer página aberta no navegador do balcão que carregue o mesmo SDK consegue, em princípio, enumerar o leitor e pedir captura. A tela de colher só deve ficar aberta com o balcão presente.

**Comparação 1:1 no reconhecimento de firma: PRÓXIMA ETAPA.** O SDK web não traz comparador (a comparação da DigitalPersona é do SDK nativo ou do servidor de autenticação dela). Quando vier, entra como **ALERTA** ao lado do reconhecimento — nunca como trava: recusar o ato é decisão de quem está no balcão, como no alerta de fraude.

### Fatia 3 — XML e envio ao CCN

| arquivo | o que faz |
|---|---|
| `ccn.py` | montar XML XSD v4, enfileirar, enviar, ler erros |
| `notas_schema.py` | tabela `nt_ccn_envios` (cartao_id, quando, status, import_id, erro) |
| `ccn.cred` | `X-Api-Key` e `X-Subscription`, ao lado de `selador.cred` |
| `tests/test_ccn_xml.py` | XML contra o XSD; HTTP em dublê |
| `tests/test_ccn_envio.py` | CCN fora do ar = recado, cadastro não quebra |

Homologação primeiro: `https://pessoas-hml.e-notariado.org.br`. Produção só depois de import `Successful` na hml. O oficial pede chave em `servicos@cnbcf.org.br` e o acordo de cooperação (esta casa é o fornecedor).

Lote do acervo: CPF + nome + ficha dos 2.956 que já têm imagem. Sem os 462 moldes. Sem foto inventada. Fora do horário de balcão. Arquivo < 30.000 KB.

### Fatia 4 — o termo usável (#38)

| arquivo | o que faz |
|---|---|
| `atribuicoes_web.py` `rcpn_folha` / `rcpn_termo` | gerar **mostra** `rc_termo.montar` quando `teor` está vazio |
| templates da folha/termo | some o parágrafo que explica as três colunas |
| `rc_termo.py` / `rc_modelos_do_livro.py` | nascer, casar, morrer na mesma estrutura; óbito nos 12 incisos do art. 255 |
| `tests/test_rc_termo.py` (e o que já existir de folha) | prévia com teor vazio; freeze só no confirmar; três espécies |

Assento importado: prévia não grava. Assento novo: `congelar` uma vez, como hoje. Papel da folha: paisagem, três colunas, frente e verso — exigência da COGEX, não sai.

### O que este projeto de código recusa

- Tabela `pessoas` / `clientes` paralela a `nt_cartoes`
- Blob de imagem no SQLite
- Mandar `nt_cartoes.biometria` ao CCN
- Licença por estação do site do CCN
- HTTP 500 porque o CCN ou o leitor falhou
- `ATUALIZAR_SISTEMA` antes do lote de testes desta pasta estar verde
- Mexer em `C:\Program Files\CartorioGestao` por cima do instalado


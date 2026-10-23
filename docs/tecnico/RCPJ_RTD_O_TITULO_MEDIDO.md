# O TÍTULO NO RCPJ E NO RTD — o que o E-Ofício ensina, medido

Escrito em **03/09/2026**, atendendo ao pedido do oficial:

> «vamos melhorar o RCPJ e RTD. Preciso que o sistema receba o título em
> protocolo, esteja disponível para analisar no visualizador de pdf direto no
> sistema, disponível para baixar, se positiva a qualificação possa imprimir a
> etiqueta de registro para o título apresentado em papel, ou encaminhamento
> pela ONRTDPJ para os eletrônicos. **Verificar o que o e-ofício pode nos
> ensinar.**»

Tudo o que segue foi **medido** no `acervo_eoficio.sqlite3` (229 tabelas), aberto
em modo `ro`. Onde a medição não respondeu, está escrito que não respondeu.

---

## 1. O protocolo é UM, e serve as seis atribuições

`tbProtocoloGeral` — **21.360 linhas**, com `intAtribuicao` dizendo de quem é
cada uma:

| atribuição | protocolos |
|---|---|
| 1 · Notas | 13.176 |
| 6 · RCPN | 4.862 |
| 5 · Registro de Imóveis | 2.838 |
| **4 · RTD** | **231** |
| 2 · Protesto | 212 |
| **3 · RCPJ** | **38** |
| 0 · sem atribuição | 3 |

O número tem a forma `AAAA.MM.N` — `2026.08.155`, `2025.12.264`. Ele carrega
interessado, documento, telefone, e-mail, assunto, anotação, prazo, setor,
depósito prévio, gratuidade e base de cálculo.

**Nesta casa esse protocolo já existe**: é o `cx_protocolos` do balcão, com a
coluna `atribuicao` prevendo `RTD` e `RCPJ` desde sempre. O que faltava era a
ponte — `rg_titulos.protocolo_geral_id`, do mesmo feitio de
`cx_protocolos.ri_protocolo_id`, que já liga a prenotação do RI.

> **E o RCPJ nunca apareceu lá.** Medido na produção: `cx_protocolos` tem 38
> protocolos de `RTD` e **zero** de `RCPJ`, embora o comentário do esquema
> preveja os dois.

---

## 2. E o título tem um SEGUNDO número, que é o da atribuição

`tbRegistroTD` guarda **dois**:

```
strProtocoloGeral   '2026.01.164'   o do balcão, que serve as seis
intProtocolo         1275           o do RTD/RCPJ
```

E os contadores dos dois estão em `tbTD_Propriedade`:

| | |
|---|---|
| `intProtocolo_RTD` | **1.275** |
| `intProtocolo_RPJ` | **1.273** |

**São dois contadores, e não um.** Um só faria o protocolo do RCPJ pular por
causa do movimento do RTD — e é o segundo número que vai na etiqueta e na
certidão.

**O Livro de Protocolo de cada um já estava declarado nesta casa, e ninguém
escrevia nele.** `livro_nucleo` traz `PJ_PROTOCOLO` e `TD_PROTOCOLO` desde
21/08/2026 — diários, com termo contínuo, citando exatamente esses dois
números — e **nenhuma tela jamais os usou**. É a «função pronta que nenhuma
tela chama» outra vez; `rg_titulo.receber` é a tela que faltava.

---

## 3. O E-Ofício abria protocolo e NUNCA O FECHAVA

Este é o achado que mais governou o desenho.

| medição | resultado |
|---|---|
| `tbProtocoloGeral.bitFinalizado` | **0 em 21.360 de 21.360** |
| `dtmFinalizado` preenchida | **0** |
| `intSituacaoPG` | **1 («Aberto») em 21.360 de 21.360** |
| ocorrências de situação | **9.987, todas com o código 1** — «Aberto protocolo geral» |
| trâmites entre setores | **9.988, todos do setor 0 para o setor 0** |

`tbProtocoloGeral_Situacao` declara **cinco** estados — Aberto, Suspenso,
Finalizado, Cancelado, Parcialmente Finalizado. `tbSetor` tem dois setores
cadastrados, com responsável e tudo. **A máquina de situação, de trâmite e de
finalização existia inteira e nunca foi exercitada.**

> **Um protocolo que só abre é um diário, e não um protocolo.**

É por isso que as seis situações de `rg_titulos` não são enfeite, e há teste —
`test_toda_situacao_declarada_tem_quem_a_produza` — que percorre as seis e
**produz cada uma**. Situação que nenhum caminho alcança é trava esperando um
estado que nada cria: o defeito que `caixa_protocolo` consertou em 28/08/2026.

---

## 4. O título apresentado NÃO TINHA LUGAR no E-Ofício

Esta é a maior lacuna que o pedido do oficial fecha, e ela não é pequena — sem
o documento na tela, quem qualifica não tem o que ler.

**As imagens que existem são do LIVRO, e não do título.** `tbTD_Img`, 155
linhas, amarradas ao **registro** (`intnumeroregistro`), com folha e
frente/verso: é a digitalização do livro **depois** do ato.

**E as duas colunas do documento do apresentante estão vazias:**

| coluna de `tbRegistroTD` | preenchida |
|---|---|
| `strPet` (a petição) | **0 de 72** |
| `strPetImg` (a imagem dela) | **0 de 72** |
| `memInteiroTeor` | 47 de 72 |
| `strApresentante` | 72 de 72 |

**O título como entrou não era guardado.**

### E os caminhos dos arquivos apontavam para fora da casa

```
\\servidor\C11\RTD_RPJ\PJ_321_0.jpg
C:\Users\<usuario>\Desktop\PJ_345_0.png      ← a Área de Trabalho de alguém
```

Metade das 155 imagens aponta para um Desktop. `tbTD_Propriedade.
strPastaPrincipal` confirma: `C:\Users\<usuario>\Desktop`.

Aqui o arquivo vai para `archive_root`, pela `attachments` — a mesma tabela do
expediente, da tarefa, da prenotação do RI e do termo do RCPN. **Não se cria a
quinta**, e é a única pasta que o backup alcança.

---

## 5. A etiqueta de registro está medida — 90 × 40 mm

`tbTD_Propriedade.id_Configuracao_Etiqueta_Registro` = **3**, que aponta para a
terceira linha de `tbPropriedades_Etiquetas`:

| | |
|---|---|
| `intLargura_Etiqueta` | **9,0** |
| `intAltura_Etiqueta` | **4,0** |
| `strFontePadraoEtiqueta` | Arial |
| `intTamanhoFonteEtiquetaCorpo` | **6** |
| `intTamanhoFonteEtiquetaCabecalho` | 6 |
| `…CabecalhoNomeCartorio` | 10 |
| margens esq. / dir. / sup. | 0,7 / 0,7 / 1,5 |
| QR: X / Y / escala | 290 / 65 / 70 |

E no próprio controlador do RTD/RCPJ:

| | |
|---|---|
| `bitETI_ComCabecalho` | **1** — a etiqueta leva cabeçalho |
| `intETI_QLE` | **11** linhas |
| `intETI_QMCH` | **60** caracteres por linha |
| `strPortaEtiqueta` | `LPT1` |

**É outra tira que a do reconhecimento de firma**, que esta casa usa a
100 × 30 mm com corpo 8. Por isso `etiqueta.py` passou a ter **configurações
nomeadas** — que é a forma a que o próprio E-Ofício chegou: as três de
`tbPropriedades_Etiquetas` são «Reconhecimento de Firma», «Termo de Presença» e
«Autenticação», cada uma com as suas margens e o seu corpo.

**As 11 linhas de 60 caracteres fecham a conta**: 11 linhas a 6 pt com
entrelinha 1,15 dão ~26,8 mm, e a tira tem 36 mm depois das margens. O corpo 6
não foi escolhido — foi medido e conferido.

> **A CONFERIR: a unidade das margens.** `9.0` e `4.0` são centímetros sem
> dúvida razoável. As margens (`0,7`, `1,5`) o E-Ofício não diz em que unidade
> guarda, e 1,5 cm de margem superior numa tira de 4 cm comeria 37% dela.
> **Não se adota o que não se entendeu**: a margem padrão daqui são os mesmos
> 2 mm da etiqueta de firma, que é medida desta casa.

> **E `Etiquetas.Teor` é um RTF VAZIO.** A tabela do texto da etiqueta tem uma
> linha só, `Tipo 0`, com um RTF sem conteúdo nenhum. O corpo da etiqueta vinha
> do código do E-Ofício, e não de um modelo — não há teor a imitar.

---

## 6. Sobre a ONRTDPJ — o E-Ofício não ensina, e o contrato está PÚBLICO

Esta seção **foi reescrita no mesmo dia**, e o registro de como ela estava vale
tanto quanto o que ela diz agora.

### O que se mediu no acervo, e continua verdade

| busca no acervo do E-Ofício | resultado |
|---|---|
| tabela com `rtdpj` no nome | **zero** |
| tabela com `central` no nome | **zero** |
| coluna com `rtdpj` no nome | **zero** |
| coluna com `onr` no nome | **3, todas do Registro de Imóveis** |

O único ONR que existe lá é o do RI: `tbONR_Propriedades` guarda duas pastas —
`\\Servidor\c11\ONR\xmls` e `E:\C11\ONR\INDICADOREAL` —, arquivos
gravados em disco e enviados à mão. É o que `ri_onr.py` já faz nesta casa.
**Aquela casa nunca usou a Central do RTDPJ.**

### A conclusão que eu tirei disso, e que estava errada

> «Sem precedente e sem contrato, escrever aqui um endereço, um nome de
> operação ou um formato de mensagem seria inventar número — e nesta casa
> número não se inventa.»

**A medição estava certa e a conclusão estava errada.** O E-Ofício não tinha o
que ensinar; **o mundo tinha**. O contrato da Central está público, exatamente
como o WSDL da CRA estava:

```
https://centralinside.rtdbrasil.org.br/            a documentação (Swagger UI)
https://centralinside.rtdbrasil.org.br/swagger/docs/v1    o contrato
```

**É a lição deste projeto pela sexta vez, agora pelo lado da fonte: não achar
onde eu procurei não prova que não existe.** As cinco anteriores foram colunas
do acervo — o `codigoAto` dentro do `memJson`, os contadores de
`tbPropriedadeRCPN`, o `intCodigoIBGE`, o `strTipoMorte`, o `strMotivo`. Esta
foi uma **fonte inteira**. E o que desfez não foi releitura: foi **procurar
noutro lugar**.

### O contrato, medido em 03/09/2026

Guardado em `FONTES_EXTERNAS/onrtdpj/swagger_v1.json` — 82.068 bytes — que fica
**fora** de `SERVIDOR/INSTALAR_CARTORIO_GESTAO` e por isso **não viaja no
`.cgu`**, como a biblioteca do Gentil e os XSDs da CRA.

| | |
|---|---|
| versão | **Swagger 2.0** |
| host | `centralinside.rtdbrasil.org.br` |
| schemes | `["https"]` — sem `basePath` |
| título | «Central ONRTDPJ - API Cartórios v1» |
| caminhos | **81** |
| definições | **100** |

**A AUTENTICAÇÃO É UM TOKEN NO CABEÇALHO**, e não usuário e senha:
`securityDefinitions.Token` é `apiKey`, `in: header`, `name: Authorization`. A
página diz de onde ele sai, com todas as letras:

> «O cartório deve utilizar o token gerado na própria Central RTDPJBrasil, no
> menu Serviços > Envio Extrato SINTER. O token é o mesmo utilizado nessa outra
> API do SINTER.»

E diz o que fazer sem acesso: cadastrar-se como pessoa física em
`https://www.rtdbrasil.org.br/autenticacao/login` e pedir por e-mail a
`atendimento@onrtdpj.org.br` que o CPF seja vinculado ao cartório.

### Três coisas que o contrato NÃO diz, e ficam ditas

**1. Ele declara o esquema de segurança e não o aplica a operação nenhuma.**
Medido: não há `security` no documento nem em nenhuma das 81 operações. Logo
**quais chamadas exigem o token não está no contrato** — está na prosa. O
módulo manda o cabeçalho em todas, e há teste que fica vermelho no dia em que
passarem a declarar.

**2. Nenhum corpo declara campo obrigatório.** `required` vem **vazio nas cem
definições** — a mesma situação dos `/v2` da CENPROT. **Não se inventa
obrigação que o contrato não declara**: o que o módulo recusa é a chamada que
não pode funcionar (pedido sem protocolo age sobre nada), e o código diz que
isso é regra da casa, não do contrato.

**3. `POST /api/arquivo` declara `consumes: ["application/form-data"]`, e esse
tipo não existe.** O parâmetro é `in: formData, type: file`, e arquivo em
formulário viaja em `multipart/form-data`. É erro de digitação do contrato,
como os dois da CENPROT; mandar o que está escrito faria o servidor não achar
parte nenhuma. Há teste que fica vermelho quando corrigirem — a mesma decisão
do `http://` no WSDL da CRA.

### E há um ambiente só

O contrato declara **um** host. **Inventar um endereço de homologação seria o
pior tipo de número inventado**: quem o usasse acharia que está testando
enquanto fala com a Central de verdade. A tela diz isso em vermelho.

### O que foi construído — 10 dos 81 caminhos

| operação | serve a que parte do pedido |
|---|---|
| `GET /api/pedido/pendentes` | **é por aqui que o título eletrônico chega** |
| `GET /api/pedido/{protocolo}` | a situação, ao trazer |
| `POST /api/notadevolutiva` | a **qualificação negativa** chegando a quem apresentou |
| `GET /api/v2/notadevolutiva/{protocolo}` | as notas de lá, com link e nome do arquivo |
| `POST /api/pedido/registrar` | comunicar o registro **já lavrado aqui** |
| `POST /api/pedido/orcamento` | o valor |
| `POST /api/pedido/cancelar` | com motivo escrito |
| `POST /api/arquivo` | subir o documento |
| `GET /api/pedido/tiposregistro` | o catálogo, lido de lá e **não copiado** |
| `GET /api/cartorio/{cns}` | o **teste de ligação** — busca pura, não mexe em pedido |

Os outros 71 servem coisas que esta serventia não faz por ali — busca e
apreensão, viabilidade, DBE, CDT, condomínio. **Declarar os 81 daria oitenta e
uma funções sem chamador**, que é o defeito mais repetido deste projeto.

**O SISTEMA NÃO REGISTRA NA CENTRAL: ELE COMUNICA O QUE JÁ LAVROU.** O registro
é o do livro desta casa, com a folha e a numeração dela; um botão que
informasse a Central sem o ato lavrado poria no mundo um registro que o livro
não tem. E o que sobe na nota devolutiva é **o texto que foi lavrado aqui**, e
não um digitado de novo: dois textos para a mesma exigência divergiriam, e o
que a Central mostrasse não seria o que a serventia decidiu.

**A ATRIBUIÇÃO É ESCOLHIDA POR QUEM TRAZ, E NÃO DEDUZIDA.** O contrato traz
`Servico.Especialidade`, e **o que ela vale para separar RTD de RCPJ não foi
medido** — não há um pedido real desta serventia para conferir. Deduzir por
semelhança poria o título no livro errado, e livro errado só aparece quando a
certidão sai.

**O TOKEN NÃO ENTRA NO BANCO** — `onrtdpj.cred`, ao lado de `cra.cred`,
`cenprot.cred`, `selador.cred` e `claude.cred`. O banco viaja no backup, e o
backup desta serventia já saiu daqui.

---

## 7. Os livros, e a dúvida do levantamento resolvida

`LEVANTAMENTO_QUATRO_ATRIBUICOES.md` deixou aberto: *«a inspeção fala em Livro
B-7 do RTD, e o controlador diz `intLivroAtual_RTD: 2`. Preciso abrir
`livroTDPJ` para desempatar.»* Aberto:

| Id | atribuição | volume | tipo de livro | ativo | aberto em |
|---|---|---|---|---|---|
| 1 | RCPJ | 4 | Livro A | não | — |
| 2 | RCPJ | 5 | Livro A | sim | — |
| 1003 | RCPJ | **6** | Livro A | sim | 03/07/2026 |
| 3 | RTD | **7** | Livro B | sim | 27/06/2023 |
| 1004 | RTD | **8** | Livro B | sim | 03/07/2026 |

**A inspeção estava certa: «Livro B-7» é o volume 7 do Livro B do RTD.** E os
registros confirmam — `tbRegistroTD` traz `strLivro = '7'` nos 41 do RTD.

**O `intLivroAtual_RTD: 2` do controlador NÃO é o volume**, e o que ele é
continua **A CONFERIR**: os volumes do RTD são 7 e 8, e nenhum é 2. O
`intLivroAtual_RPJ: 4` bate com o volume 4 do RCPJ, que está inativo — o que
sugere que os dois campos ficaram para trás.

### E há um defeito de dado no acervo, à vista

O volume 5 do RCPJ está escrito **de duas formas**:

| `strTipoRegistro` | `strLivro` | registros |
|---|---|---|
| PJ | `'04'` | 2 |
| PJ | `'05'` | 22 |
| PJ | `'5'` | 7 |

`'05'` e `'5'` são o mesmo volume. Quem contar por `strLivro` conta dois livros
onde há um. `rg_registros.volume` guarda o que veio, e a divergência fica
visível em vez de corrigida em silêncio.

---

## 8. As naturezas do RTD/RCPJ mal foram usadas

`tbNaturezaReg`, que é para onde `tbRegistroTD.intCodigoNR` aponta, tem **três
linhas**: `NOTIFICAÇÃO`, `NAT` e `REGISTRO DE ATA GERAL EXTRAORDINÁRIA`.

Não há vocabulário a importar. Por isso `rg_titulos.natureza` é **texto livre**,
como `rg_registros.natureza` já era.

---

## 9. O que foi construído

| | |
|---|---|
| `rg_schema.py` | `rg_titulos`, `rg_qualificacoes`, `rg_encaminhamentos`, mais `rg_registros.titulo_id` e as duas colunas da etiqueta em `rg_atos` |
| `rg_titulo.py` | receber · qualificar · registrar · encerrar · registrar a passagem |
| `rg_web.py` | a fila, a ficha com o visualizador, a nota devolutiva, a etiqueta e o ajuste dela |
| `caixa_protocolo.py` | abre o protocolo geral `AAAA.MM.N`; cada título novo fica ligado a ele e recebe também o número próprio do protocolo RTD/RCPJ |
| `rg_titulo.atualizar` | completa depois da apresentação os dados que puderam entrar vazios, sem alterar número, data ou atribuição; sincroniza os dados comuns com o protocolo geral |
| `arquivo_visivel.py` | o que o navegador abre na tela, e o que baixa |
| `etiqueta.py` | as medidas das duas etiquetas da casa, uma máquina e duas configurações |
| `/arquivo/<id>/ver` | **conserta o relato #25 na atribuição vizinha** — ver abaixo |

### O defeito antigo que isto conserta de passagem

O relato #25 do oficial, de 29/08/2026, pedia *«anexar documentos e
**visualizar** esses documentos»*. `ri_documentos.e_imagem` nasceu para decidir
isso, com o comentário «QUEM LAVRA PRECISA VER, E NAO BAIXAR», e a tela do RI
põe `target="_blank"` no link quando o arquivo é PDF ou imagem.

**E a única rota que servia arquivo mandava `as_attachment=True`** — o
navegador baixava, sempre. A metade que decide estava pronta e a metade que
serve nunca soube dela. `/arquivo/<id>/ver` fecha isso para a casa inteira.

### A lista do que abre na tela é curta, e é de segurança

Arquivo servido **em linha** roda na **origem do sistema**: um `.html` ou um
`.svg` enviado por terceiro traria o script dele para dentro da sessão de quem
está no balcão, com o cookie de login à mão — e o balcão recebe arquivo de fora
todo dia.

Abrem na tela: **pdf, png, jpg, jpeg, gif, webp, bmp**. Tudo o mais baixa.

**`svg` é a armadilha e fica de fora**: é imagem, e é XML com `<script>`.
`tif`/`tiff` também, por outro motivo — quase nenhum navegador os desenha, e
tela em branco é pior que o botão de baixar.

E quem serve manda `X-Content-Type-Options: nosniff` e uma política que proíbe
script e moldura de fora. **A lista decide o que se oferece; os cabeçalhos
protegem o que se serviu.**

---

## 10. O que continua faltando, e é pergunta e não trabalho

1. **O token da Central ONRTDPJ.** A especificação **apareceu** (seção 6) e o
   transporte está construído; o que falta é o segredo, que só o cartório pode
   gerar: entrar em `rtdbrasil.org.br`, ir em **Serviços → Envio Extrato
   SINTER** e copiar o token. Sem acesso àquele ambiente, cadastrar-se como
   pessoa física e pedir a `atendimento@onrtdpj.org.br` que o CPF seja
   vinculado à serventia.

   **E há uma coisa que só se responde com um pedido real na fila**: o que a
   `Servico.Especialidade` do contrato vale para separar RTD de RCPJ. Enquanto
   não se souber, quem traz o pedido escolhe a atribuição — e a tela diz por
   quê.
2. **A unidade das margens de `tbPropriedades_Etiquetas`.** Resolve-se com uma
   tira na mão e uma régua.
3. **O que é o `intLivroAtual_RTD: 2`** do controlador, que não bate com
   volume nenhum.
4. **O orçamento automático enviado à Central.** Selo e custas do registro já
   podem ser lançados na mesma transação do ato. A tela da ONRTDPJ ainda pede o
   valor do orçamento porque o contrato da Central não informa como converter
   o serviço pedido na composição de custas desta serventia.

---

## 11. O que eu decidi NÃO fazer, e por quê

**A carga do acervo não cria título.** `tbRegistroTD` traz `intProtocolo` em
**72 de 72** e `strProtocoloGeral` em **70 de 72** — é dado real, e seria
tentador criar uma linha em `rg_titulos` para cada registro do acervo com esses
números.

**Não se faz, por duas razões que se somam:**

1. **Seria fabricar uma história que não aconteceu.** O título entraria como
   `APRESENTADO`, sem qualificação nenhuma, e sairia `REGISTRADO` — inventando
   um caminho pelo qual aqueles 72 registros nunca passaram neste sistema. É a
   regra de `ri_numeros_do_teor`: **não se cria ato a partir do que se leu**.
2. **E ocuparia lugar no Livro de Protocolo.** `rg_titulo.receber` chama
   `escrituracao.reservar`, que numera. Setenta e dois títulos do acervo
   entrando pelo livro de hoje reescreveriam a numeração — é exatamente o que
   `acervo_carga` já evita ao não chamar o núcleo para os atos que vieram do
   livro físico.

**O que se perde com isso, dito:** o `intProtocolo` daqueles 72 registros
continua **fora do sistema**, porque `rg_registros` não tem coluna para ele. É
uma lacuna real, e é declarada aqui em vez de resolvida por conta própria —
trazê-lo é coluna nova mais passada de carga, e o pedido do oficial era sobre o
título que **chega**, não sobre o que já está no livro.

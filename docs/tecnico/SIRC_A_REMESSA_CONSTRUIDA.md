# A remessa do SIRC — construída em 29/08/2026

> **É o prazo mais curto desta casa: um dia útil.** E é o destino que alcança
> mais coisa — sete espécies, contra três da CRC.

## A obrigação, na letra do art. 225 do Código de Normas do TJMA

> «O oficial de registro civil remeterá, **no prazo de até 1 (um) dia útil**, ao
> INSS, por meio do Sistema Nacional de Informações de Registro Civil (SIRC),
> (…) a relação dos **nascimentos, dos natimortos, dos casamentos, dos óbitos,
> das averbações, das anotações e das retificações** registradas na serventia.
>
> § 1º Para os Municípios que não dispõem de provedor de conexão à internet (…)
> fica autorizada a remessa em até **05 (cinco) dias úteis**.
>
> § 3º No caso de **não haver sido registrado nenhum** nascimento, natimorto,
> casamento ou óbito, deverá o titular **comunicar este fato ao INSS, até o 5º
> (quinto) dia útil do mês subsequente**.
>
> § 4º O descumprimento (…) e o fornecimento de **informação inexata**
> sujeitarão o titular (…) à penalidade prevista no **art. 92 da Lei nº
> 8.212/1991** (…) e à **ação regressiva proposta pelo INSS**, em razão dos danos
> sofridos.»

**A sanção tem dois lados, e o segundo é o que muda o desenho do módulo.** Não
mandar é punido; mandar **errado** também — e com ação regressiva, que é o INSS
cobrando do delegatário o prejuízo. É por isso que o que está incompleto **fica
retido com o motivo escrito**, em vez de ir num arquivo bem formado e falso.

## O que a remessa leva, e por que isso amarra dois módulos

Sete coisas. As quatro primeiras são registros e moram em `rc_assentos`; as três
últimas são atos e moram em `rc_atos`:

| | onde mora |
|---|---|
| nascimento, natimorto, casamento, óbito | `rc_assentos` |
| **averbação, anotação, retificação** | `rc_atos` |

**Uma lista que olhasse só os assentos deixaria a averbação de fora sem ninguém
ver** — e é justamente a metade que o SIRC pede e a CRC não. Isso liga esta
remessa direto ao módulo de anotações (`rc_anotacao.py`): toda anotação que o
art. 367 manda fazer é também uma linha que o art. 225 manda mandar, no dia
seguinte.

`pendentes_de_remessa()` lê as duas tabelas e devolve **do mais antigo para o
mais novo**: com prazo de um dia útil, o que está esperando há mais tempo já
estourou, e é por ele que se começa.

## Os limites do arquivo — medidos, não escolhidos

Do *SIRC – Recomendações Técnicas*, 121 páginas da Dataprev, em
`FONTES_EXTERNAS/SIRC_manual_recomendacoes_tecnicas.pdf`:

| | |
|---|---|
| formato | XML válido contra o XSD |
| codificação | **UTF-8** |
| tamanho | no máximo **1024 KB** |
| registros | no máximo **250 por arquivo** |
| compactação | GZIP |
| intervalo | no mínimo **1 minuto** entre envios |

**O teto de 250 decide a forma do módulo.** Não é detalhe de transporte:
estourar não faz a Dataprev aceitar 250 e recusar o resto — **ela recusa o
arquivo inteiro**. Por isso `montar()` já devolve os lotes prontos, e a tela
mostra em quantas partes a remessa vai.

**E o limite de tamanho é em BYTES, não em caracteres.** «JOSÉ» ocupa 5 bytes em
UTF-8 e 4 caracteres — e no Registro Civil quase todo nome tem acento. Medir por
caractere deixaria passar arquivo que a Dataprev recusa. Há teste que compara o
tamanho de `JOSÉ` com o de `JOSE` e exige a diferença de um byte.

## A diferença que separa este envelope do da CRC

É a razão de haver dois montadores, e não uma montagem que sirva aos dois:

| | |
|---|---|
| **CRC** | tag em branco **já quer dizer** «nulo ou Ignorado(a)» |
| **SIRC** | é preciso **marcar** explicitamente, e o marcador **não pode** estar presente quando o campo está cheio |

> «Quando um campo não estiver informado, o **marcador de campo ignorado deve ser
> informado**. Analogamente, o marcador **não pode estar informado** quando
> houver preenchimento do campo.»

Uma montagem única acertaria um envelope e erraria o outro **exatamente onde o
dado falta** — que é onde os dois discordam. `campo()` resolve isso num lugar só:
o valor **ou** o marcador, nunca os dois, nunca nenhum.

### O marcador não se calcula: ele foi medido

São **52 marcadores** no XSD, e o nome de cada um concorda em gênero com o
**substantivo do campo**:

```
nomeIgnorado          mas   dataNascimentoIgnorada
sexoIgnorado          mas   horaNascimentoIgnorada
documentosIgnorado    mas   idadeIgnorada
tipoMorteIgnorado     mas   corPeleIgnorada
```

Uma função que colasse `"Ignorado"` no fim do nome acertaria uns e erraria os
outros — **e erraria calada**, porque o XML continua bem formado e o arquivo só
volta recusado pela Dataprev. Por isso `MARCADOR_IGNORADO` é tabela, e há teste
que exige os dois gêneros.

### E a regra tem dois lados — o segundo é o que escapa

Faltar o marcador quem monta percebe. **Sobrar o marcador ao lado de um campo
cheio ninguém percebe**, porque a linha continua completa e o XML continua bem
formado. `conferir_marcadores()` existe para esse segundo lado, e a tela o chama
antes de oferecer o arquivo.

## Duas coisas mais que não se herdam da CRC

**A data vai em `dd/mm/aaaa`**, e o banco guarda `aaaa-mm-dd`. Mandar o ISO
produz arquivo bem formado que a Dataprev recusa — inteiro, e não a linha. E data
ilegível volta **vazia**, virando marcador de ignorado: inventar um dia para uma
data que ninguém sabe seria afirmar ao INSS uma coisa falsa.

**O sexo é a palavra inteira**, e são seis valores: `MASCULINO`, `FEMININO`,
`NAO_BINARIO`, `OUTROS`, `NAO_DECLARADO`, `IGNORADO`. A CRC escreve `M`, `F` e
`I`. Usar um vocabulário pelo outro é o mesmo tipo de erro do envelope.

## O defeito que a declaração de mês vazio achou

`_texto` era `str(v or "").strip()` — o reflexo de sempre. **Ele come o `0` junto
com o `None`**, porque zero é falso em Python. Aqui isso não é estilo: com o SIRC
exigindo marcador para o campo sem valor, uma **quantidade zero** sairia
declarada ao INSS como «não sei», que é afirmação diferente de «zero» — e o
arquivo em que a quantidade é zero é justamente a declaração de inexistência de
movimento.

Peguei montando o § 3º. Está consertado e tem teste.

## Mês sem movimento também se comunica

**É a obrigação que mais se esquece, e justamente porque não há trabalho que a
lembre**: não houve registro, não houve remessa, e ninguém repara na falta. O
§ 4º não distingue — a sanção alcança o descumprimento, e não haver o que mandar
só deixa de ser descumprimento se a declaração for feita.

A tela tem o campo do mês e o botão, ao lado da lista.

## O que este módulo não faz

**Não envia — mas o caminho por senha não exige A3, e isto corrige o que
este documento dizia até 14/09/2026.**

Estava escrito aqui que o web service "pede usuário e senha, ou certificado
A3" — como se as duas fossem a mesma dificuldade. **Não são.** O manual
descreve dois Web Services distintos:

| | endereço | autenticação |
|---|---|---|
| `/SircWs/Movimento` | `sirc.dataprev.gov.br/SircWs/Movimento?wsdl` | **usuário e senha**, SOAP/HTTPS simples |
| `/SircWs/MovimentoCertificadoDigital` | idem + `MovimentoCertificadoDigital` | certificado **A3** + WS-Security + XML Signature |

Só o segundo exige o token físico. O WSDL do primeiro é **público**, e foi
lido em 14/09/2026: **9 operações**, uma por espécie e ação —
`enviarMovimentoNascimento`, `enviarMovimentoCasamento`,
`enviarMovimentoObito`, `enviarMovimentoCancelamento`,
`declararInexistenciaMovimento`, e os quatro `validar*` irmãos — cada uma
recebendo `{cns, usuario, senha, conteudo}`, com `conteudo` sendo
exatamente o XML que este módulo já monta.

**A separação por espécie que `montar()` já faz não é só do arquivo — é da
própria API**: não existe operação genérica que aceite duas espécies
juntas, e é por isso que um lote nunca pode misturar nascimento com
casamento.

Este módulo continua **só montando, sem chamar a rede** — a chamada em si
(o cliente SOAP, a guarda da credencial fora do banco, o histórico de
envio) é a próxima peça, no mesmo padrão de `centrais_cred.py` que a CRA e
a CENPROT já usam. Só que aqui o caminho mais simples não depende de
hardware nenhum.

Há teste que varre o módulo procurando `import requests`, `import urllib`,
`import gzip` e `import socket`, e outro que varre os nomes públicos procurando
`enviar`, `transmitir` e `assinar` — a lição do `a_enviar`, que era uma lista e
foi lido como ação.

## O CASAMENTO ENTROU EM 14/09/2026 — validado contra o XSD, não só lido

Medido contra `registroCasamento` (seção 8.3 do manual, extraído e limpo dos
artefatos de PDF): **638 de 638** casamentos reais desta serventia validam
sem erro. Achados que só a validação de verdade revelou:

- **A ordem dentro de `<conjuge1>`/`<conjuge2>` não é a intuitiva.** O
  `xs:sequence` de `conjugeAbstrato` põe `documentosConjuge` +
  `cpfConjugeIgnorado`, depois as duas `filiacoesConjuge`, só depois
  `nome`, e por último `sexo` — a primeira versão pôs nome e sexo primeiro,
  ficou bem formada, e a Central recusaria por estrutura, não por conteúdo.
  É a mesma família de erro que o nascimento já tinha ensinado
  (`_registro()`), um nível mais fundo.
- **`filiacoesConjuge` tem `minOccurs="2"`**, como `filiacoesNascimento` —
  sempre duas, mesmo com um genitor desconhecido.
- **O CPF do cônjuge não é campo direto**: vai dentro de `documentosConjuge`
  com `tipo=CPF`, `dono=CONJUGEn` — ao contrário da CRC, cujo `TIPO_DOC` não
  enumera CPF.
- **`regimeCasamento` tem vocabulário PRÓPRIO, diferente do da CRC.** A CRC
  enumera `SEPARACAO_LEGAL_BENS`; o SIRC não. Reaproveitar o de-para da CRC
  produziria um valor que o XSD do SIRC recusa — `regime_casamento_sirc()` é
  um de-para novo, com o mesmo caso especial de 1977 (Lei do Divórcio) que
  a CRC já resolvia para "comunhão de bens" sem qualificação.
- **`CASAMENTO_RELIGIOSO` usa o MESMO envelope do civil** — não é um
  terceiro `movimentoXTO`; muda só o `tipoLivro`, que já vem da matrícula.

**E a conferência de marcadores ganhou um segundo nível de aninhamento.** O
casamento tem `registro → conjuge1/conjuge2 → filiacoesConjuge` — dois
níveis, contra um do nascimento —, e a mesma tag (`sexo`/`sexoIgnorado`)
aparece nos três. `_conferir_um_pedaco` virou `_conferir_recursivo`, que
desce nos filhos de cada nível em vez de assumir só um.

## O ÓBITO ENTROU EM 14/09/2026 — e achou o defeito irmão do casamento

Medido contra `registroObitoAbstrato` (seção do óbito do manual, extraído e
limpo dos artefatos de PDF) e contra o exemplo real (seção 7.2): **398 de
398** óbitos reais desta serventia validam sem erro. O achado desta vez não
foi de ordem — foi um campo sem par nenhum:

- **`idade` NÃO TEM MARCADOR DE IGNORADO no XSD.** Uma entrada especulativa
  de sessão anterior (`MARCADOR_IGNORADO["idade"] = "idadeIgnorada"`), escrita
  antes de o XSD ser lido, fazia `campo("idade", ...)` inventar
  `idadeIgnorada` sempre que a idade faltava — e a Central recusaria por
  elemento inesperado. Medido: **50 dos 398** óbitos reais falhavam por
  isso antes do ajuste (o falecido sem `idade_no_fato` gravado). O corrigido
  usa `_tag()` direto, e só quando há valor — como `eleitor`, que também não
  tem par.
- **O nome do falecido tem marcador, mas ele não fica adjacente.** No
  exemplo real do manual, `<nome>`/`<nomeEspecial>` do falecido aparecem
  logo após `nacionalidadeIgnorada`, e `<nomeIgnorado>` só aparece bem mais
  adiante na sequência, perto de `nomeLocalObito`. `campo()` assume os dois
  juntos; por isso o nome do falecido usa `_tag()` direto (como o nome do
  cônjuge no casamento), e o `nomeIgnorado` — quando precisar sair — é
  emitido manualmente na posição certa.
- **`corPele` e `estadoCivil` têm vocabulário PRÓPRIO do SIRC**, sem
  «IGNORADA»/«OUTROS» — diferente dos da CRC. `COR_PELE_SIRC` reconhece
  também as duas grafias corrompidas medidas em produção (`IND�GENA`,
  `INDIG�NA` — mojibake de «INDÍGENA»), e `_estado_civil_sirc()` casa
  por raiz textual (`"CASADA(vi�va)"`, `"SOLTEIRO COM 67 ANOS..."`) —
  os 21 valores distintos medidos em `rc_pessoas.estado_civil` do papel
  FALECIDO não batem por igualdade exata.
- **`filiacoesObito` tem `minOccurs="2"`**, como `filiacoesNascimento` e
  `filiacoesConjuge` — sempre duas, mesmo com um genitor desconhecido.
- **`documentosDeclarante`/`documentosFalecido` são o mesmo `documento` do
  casamento** (`tipo=CPF`, `dono=DECLARANTE`/`FALECIDO`) — reaproveitado.
- **`ibge_local_obito`/`ibge_natureza_obito` já eram medidos** (o mesmo
  catálogo do IBGE que a remessa trimestral usa) e mapeiam direto para
  `tipoLocalObito`/`tipoMorte` — vocabulários com os MESMOS números, nomes
  diferentes.
- **Não inventa o que não mediu**: os campos de endereço do falecido e do
  local do óbito (logradouro/número/complemento/bairro em código IBGE), a
  ocupação (CBO-CNIS), o país estrangeiro, os benefícios previdenciários e
  a Declaração de Óbito (não há coluna nesta casa) saem OMITIDOS.

`FILHOS_DE` ganhou `"filiacoesObito"` no nível de fora, ao lado de
`filiacoesNascimento`/`conjuge1`/`conjuge2` — a mesma armadilha do sexo do
cônjuge/filiação, agora entre o falecido e os pais dele.

## O NATIMORTO ENTROU EM 14/09/2026 — e não com envelope próprio

O manual (seção 5.4) diz, com todas as letras: *«Para os casos em que o
falecido seja um natimorto, o tipo do livro (pertencente à matrícula do
registro) deve possuir o valor "5"»*. Não há `registroNatimorto` nem
`movimentoNatimortoTO` no XSD, e a API não tem uma operação
`enviarMovimentoNatimorto`: é o MESMO `registroObitoAbstrato` e a MESMA
`enviarMovimentoObito`/`validarMovimentoObito`, e o que muda é só o
`tipoLivro` — que já vem pronto da matrícula
(`rc_matricula.LIVRO_DA_ESPECIE["NATIMORTO"] == "5"`).

**A ÚNICA COISA QUE DIVERGIU FOI O NOME DO PAPEL DENTRO DESTA CASA.**
`rc_assento.PAPEIS_DA_ESPECIE` chama o principal de `FALECIDO` no óbito e
de `REGISTRADO` no natimorto — a mesma pessoa, dois rótulos internos. O
`dono` que vai no XML continua sendo `FALECIDO`, porque é o único valor
que o enum `donoDocumento` conhece para aquela posição; `_registro_obito()`
ganhou `PAPEL_PRINCIPAL_DO_OBITO` para escolher qual papel da casa
consultar, sem mudar o vocabulário que sai no fio.

**SEM REGISTRO REAL PARA VALIDAR EM ESCALA** — esta serventia tem **zero**
natimortos em produção —, e por isso esta espécie não tem um «398 de 398»
como o óbito teve: a garantia aqui é a letra do manual, não a medição
contra dado real. Fica registrado para quando o primeiro natimorto for
lavrado neste sistema: é o momento de confirmar contra o XSD com dado de
verdade.

## OS TRÊS ATOS ENTRARAM EM 14/09/2026 — como ALTERAÇÃO, não envelope à parte

**NÃO HÁ `registroAverbacaoInclusao` NENHUM.** Medido no manual (seção 6.1):
*«Alteração de Registro de Nascimento... Devem ser enviados TODOS OS DADOS
DO REGISTRO. Os campos que não forem enviados terão seus valores
considerados NULL»*. Averbação, anotação e retificação são blocos
(`averbacoesNascimento`, `anotacoesNascimento`, `retificacoesNascimento`, e
os equivalentes de casamento e óbito) **dentro** do mesmo
`registroXAlteracao` que carrega o registro inteiro de novo — não um
envelope próprio, e não uma operação própria na API.

- **Os atos de um mesmo assento se agrupam numa Alteração só.** Se duas
  averbações pendessem sobre o mesmo nascimento e cada uma virasse um
  envio separado, a segunda reenviaria o registro com
  `dadosComplementares=NULL` na primeira — o manual diz que campo ausente
  vira NULL, e não "mantém o que já tinha". `pendentes_de_remessa()` agrupa
  por `assento_id`; `_bloco_dos_atos()` monta todos os blocos do grupo.
- **`motivoAverbacao` é medido contra as 37 averbações reais desta
  serventia** (33 nascimento, 4 casamento): **36 são o mutirão do art. 347**
  (CPF/RG averbados em massa), que bate exatamente com `ANOTACAO_CPF` — o
  único valor do enum presente nas TRÊS espécies. A única exceção (uma
  correção de livro físico) cai em `OUTROS`, que o próprio manual reserva
  para isso — com o complemento sempre preenchido.
- **`motivoAnotacao` e o campo alterado da retificação não são medidos** —
  esta casa tem **zero** anotações e retificações em produção. As duas
  usam `OUTROS`/o texto livre de `fundamento`, que o manual aceita sempre
  que a classificação não é conhecida.
- **Validado contra o ÚNICO caso real que passa pelo filtro do acervo**: o
  assento 1231, com origem `MANUAL` (as outras 36 averbações estão em
  assentos de origem EOFICIO/ARQUIVO/IMPORTACAO, que não se remetem) —
  «Determinação do oficial à lavratura no livro físico errado», motivo
  OUTROS, validado com sucesso contra o XSD de nascimento. Casamento e
  óbito foram validados com dado sintético (zero casos reais passam pelo
  filtro), usando o mesmo motivo `ANOTACAO_CPF` e o fallback `OUTROS`.
- **`conferir_marcadores()` ganhou um backreference** (`\1\2`) para não
  casar a abertura de um `registroXInclusao` com o fecho de um
  `registroXAlteracao` do mesmo lote.

## O CANCELAMENTO DE TERMO ENTROU EM 14/09/2026 — não é um dos sete

Pedido do oficial: *"consegue fazer o soap?"*, sobre o `enviarMovimento
Cancelamento` que tinha ficado de fora por não haver dado real para medir.
**Havia**: `rc_assentos.situacao='CANCELADO'` já é o dado desta casa, com
**um caso real** — o assento 1231, a mesma história do "livro físico
errado" que já aparece como averbação.

**NÃO É UMA ALTERAÇÃO DE REGISTRO** (seção 5.7 do manual, distinta da
seção 6.1): *"esta funcionalidade deve ser utilizada apenas para termos
que não foram utilizados para fins de registro civil e/ou que foram
cancelados no livro pela serventia"*. É o oposto de uma Alteração — dizer
que o termo nunca valeu, não que o registro mudou —, e por isso tem
envelope, operação e versão de layout PRÓPRIOS:
`movimentoCancelamentoTO`/`registroTermoCancelado`, `enviarMovimento
Cancelamento`, versão **"1.1"** (não "5.0").

- **`motivo` é obrigatório no XSD** (`string350`, `minOccurs="1"`) e não
  tem coluna própria nesta casa — vem da averbação mais recente sobre o
  mesmo assento, que na prática já é onde o oficial registra por que
  cancelou. Sem averbação com fundamento, o candidato fica retido.
- **`tipoRegistroCivil` só tem três valores** (NASCIMENTO/CASAMENTO/OBITO)
  — NATIMORTO não está no enum, e cancelamento de termo de natimorto fica
  retido em vez de adivinhar qual dos dois usar.
- **Validado contra o único caso real**: assento 1231, motivo "Determinação
  do oficial à lavratura no livro físico errado (A-1 em vez de A-24)",
  válido contra o XSD extraído do manual (seção 8.5).
- **Não passa por `montar()`/`ENVELOPE_DA_ESPECIE`** — é uma lista e uma
  montagem à parte (`pendentes_de_cancelamento`/`montar_cancelamento`),
  com seção própria na tela `/rcpn/sirc`.

## A CARGA SEPARA POR ESPÉCIE — confirmado pelo manual E pela API

Os três exemplos do manual (seção 7) mostram sempre **um elemento-raiz por
arquivo** — nunca nascimento e casamento juntos. `montar()` agora agrupa os
prontos por espécie antes de lotear, e cada lote sai com um `especie` só.

## A DECLARAÇÃO DE INEXISTÊNCIA ESTAVA COM O ENVELOPE ERRADO

`declaracao_de_inexistencia()` montava `<movimento><cns>...<quantidade>0
</quantidade><inexistenciaDeMovimento>true</...>` — uma forma que **nunca
existiu** no manual. O XSD real (`declaracaoInexistenciaMovimentoServicoTO`,
seção 11) é `{competencia, declaracaoInexistenciaMovimentoCasamento,
...Nascimento, ...Obito, ...ObitoNatimorto}` — quatro booleanos
independentes, e `competencia` em `M/AAAA` sem zero à esquerda (o XSD tem o
padrão), não `AAAA-MM`.

## O CLIENTE SOAP FOI CONSTRUÍDO EM 14/09/2026 — sem A3

`sirc_cliente.py` fala com o web service por usuário e senha
(`/SircWs/Movimento`), medido no WSDL público — baixado sem credencial
nenhuma (`curl`, 200 OK) e guardado em `FONTES_EXTERNAS/sirc/Movimento.wsdl`.

- **SOAP 1.2, document/literal — não é o `rpc/encoded` da CRA21.** Cada
  operação recebe um elemento único, com os campos **por nome**
  (`{cns, usuario, senha, conteudo}`), e não posicionais.
- **Nove operações medidas**: `enviar`/`validarMovimento` para
  Nascimento, Casamento, Óbito e Cancelamento, mais
  `declararInexistenciaMovimento`. **Não há operação de Natimorto** — e
  isso concorda com `sirc_remessa.py`, que também não constrói o envelope
  dela ainda.
- **A credencial vai DENTRO do corpo XML, e não em HTTP Basic.** É por
  isso que forçar HTTPS aqui pesa mais do que na CRA: em texto puro, a
  senha viajaria dentro do próprio envelope. O WSDL declara
  `http://sirc.dataprev.gov.br:80/...`, sem o S — o sistema recusa esse
  endereço e usa `https://` sempre, como já fazia com o WSDL de
  homologação da CRA21.
- **A falha é SOAP 1.2** (`soap:Reason/soap:Text`), e não
  `<faultstring>` do 1.1 — e `SircWebServiceFault` é um `xsd:sequence`
  **vazio**, sem campo próprio para o motivo.
- **`<resultado>` volta cru.** O manual não descreve o vocabulário desse
  texto — nenhum enum, nenhum exemplo de sucesso ou recusa —, e por isso
  este módulo não interpreta o conteúdo: devolve-o para quem chamar
  decidir.
- **O SIRC entrou como sétima Central em `centrais_cred.py`**, com
  ambiente único (`PRODUCAO` — o WSDL só declara um endereço, como a
  ONRTDPJ) e forma `PAR` — mas note-se: **par por corpo SOAP, e não por
  HTTP Basic**, que é uma FORMA nova dentro do que já era `PAR`.
- **A tela `/rcpn/sirc` ganhou três botões**: validar e enviar cada
  lote pela API, e enviar a declaração de mês sem movimento — todos
  recuperáveis com a mensagem de `CredencialError` quando a senha ainda
  não foi informada, em vez de estourar.

## O MINUTO ENTRE ENVIOS ESTAVA DECLARADO E NUNCA IMPOSTO

O manual exige pelo menos 1 minuto entre um envio e outro
(`INTERVALO_MINIMO_SEGUNDOS`), e essa constante já existia — mas nunca foi
checada em lugar nenhum. Enquanto a tela só sabia BAIXAR o arquivo, o
ritmo humano de subir no SIRC-Web garantia o intervalo sozinho; desde que
`sirc_cliente.py` manda de verdade, um clique duplo ou dois lotes seguidos
podiam furar o minuto sem ninguém perceber. `_bater()` agora recusa
qualquer chamada antes do minuto passar, com a mensagem dizendo quantos
segundos faltam — depois de conferir a credencial primeiro, para a tela
apontar a falta certa.

## O PRIMEIRO CONTATO DE VERDADE — 14/09/2026, e um defeito real de TLS

Com a credencial gravada pelo oficial, o primeiro `validar()` real falhou
com `SSLZeroReturnError` (conexão fechada, EOF) — **antes mesmo de chegar
à Central**. Medido: `curl` (que usa o schannel do Windows) fala com o
servidor normalmente; só o `ssl` do Python falhava. O servidor do SIRC é
**antigo** — `Oracle-HTTP-Server Oracle-Web-Cache-11g/11.1.1.9.0`, medido
no cabeçalho `Server` de uma resposta real — e o handshake TLS não fecha
contra o `SECLEVEL` padrão do OpenSSL 1.1.1+ desta máquina.

**O conserto não desliga verificação nenhuma**: o certificado
(`*.dataprev.gov.br`, real, válido até 01/2027) continua conferido —
`contexto.set_ciphers("DEFAULT@SECLEVEL=1")` só amplia a lista de cifras
aceitas para incluir as mais antigas que este servidor entende. Depois do
ajuste, a chamada real completou e a Central respondeu com um SOAP Fault
de verdade (`Usuário/senha inválido`) — o que prova que o transporte
inteiro (envelope, TLS, parsing da falha) funciona ponta a ponta.

**A credencial que o oficial gravou foi recusada pela Central.** Não há
corrupção do lado de cá (usuário e senha saem de `centrais_cred.py` sem
espaço nem caractere estranho, do mesmo jeito que foram digitados) — a
recusa é da própria senha, e cabe ao oficial confirmar no site
`sirc.dataprev.gov.br` se ela ainda é a atual.

## O ARQUIVO PARA UPLOAD MANUAL (.mrc) — 14/09/2026

Com a API recusando a credencial, o oficial decidiu tentar a importação
manual pelo SIRC-Web. **O `.xml` que o botão já baixava não serve para
isso**: a seção 3 do manual exige o arquivo **comprimido em GZIP**,
**cifrado com AES-128-ECB** (PKCS#5, sem salt, chave = hash MD5 do CNS
**sem zeros à esquerda**) e com **extensão `.mrc`** — "quaisquer outras
extensões serão ignoradas pelo SIRC".

`sirc_remessa.arquivo_mrc(xml, *, cns)` monta esse pacote. **Validado
byte a byte contra o próprio comando de exemplo do manual**
(`openssl aes-128-ecb -k <cns sem zeros> -e -nosalt`) — com uma pegadinha
medida no processo: o **OpenSSL 3.x mudou o KDF padrão de `-k`** (de MD5
para SHA-256) desde a época em que o manual foi escrito; sem forçar
`-md md5` explicitamente, o comando do próprio manual não reproduz mais
o que ele descreve. Achado rodando o comando de verdade nesta máquina,
não supondo.

**Continua sem falar com a rede** — `arquivo_mrc()` só devolve bytes; quem
manda esses bytes para algum lugar é a pessoa que baixa o arquivo e sobe
no SIRC-Web pelo navegador, exatamente como antes desta função existir. O
teste que garante que `sirc_remessa.py` não fala com rede (`test_o_modulo_
nao_fala_com_rede_nenhuma`) teve só o `import gzip` liberado — a
proibição de rede em si (`requests`/`urllib`/`socket`) continua.

**Tela**: botão "Baixar o lote N para upload manual (.mrc)", ao lado do
`.xml` de sempre — o `.xml` continua servindo para conferência e para o
caminho por senha (`sirc_cliente.py`), que recebe texto puro dentro do
envelope SOAP.

## O PRIMEIRO CONTATO DE VERDADE COM A API, e o que ainda não se explica

Com a credencial gravada, `validar()` chegou a falar com a Central de
verdade (depois do conserto de TLS, acima) — e ela recusou com **"Usuário/
senha inválido"**, mesmo o oficial tendo confirmado que a mesma senha
funciona no site (Gerid). Testado também variando o CNS (com e sem zero à
esquerda) — mesma recusa, o que descarta erro de formato do CNS.

**Não há como confirmar a causa sem o suporte da Dataprev.** O servidor do
Web Service é visivelmente antigo (Oracle Web Cache 11g, ~2011-2012) — o
mesmo ano em que o manual registra a adoção do Gerid para autenticação —,
e é plausível que este endpoint específico nunca tenha sido migrado para
validar contra o Gerid, continuando a exigir uma credencial separada que
esta serventia nunca cadastrou. Explorado o portal SIRC-Web à procura de
alguma seção de "Web Service"/"API"/"Autorização" — não há nada assim nos
menus (`Funções de Serventia`, `Transmissão de Arquivo`); a única coisa
parecida (`Autorizar Envio de Dados por CER`) é sobre um canal de
terceiros por certificado A1, sem relação com o caminho por senha.

## O que fica pendente do oficial

- **usuário e senha do SIRC** — informar em Administrativo →
  Configurações → «Centrais — credenciais das APIs», linha SIRC. Sem
  isso, os botões de enviar/validar continuam recusando com a frase de
  onde configurar.

Não trava o que foi construído: o arquivo sempre pode ser baixado e
subido à mão no SIRC-Web, e os botões de envio pela API já existem para
o dia em que a credencial chegar.

## Os números

| | |
|---|---|
| `sirc_remessa.py` | o módulo, com o manual citado ao pé da letra |
| `tests/test_sirc_remessa.py` | **68**, incluindo os do casamento e os 8 novos do óbito |
| `tests/test_sirc_remessa_tela.py` | testes da tela, atualizados para o novo envelope da inexistência |
| tela | `/rcpn/sirc`, em Registro Civil → Remessa do SIRC |
| espécies com envelope pronto | NASCIMENTO, CASAMENTO, CASAMENTO_RELIGIOSO, ÓBITO, NATIMORTO |
| os três atos (averbação/anotação/retificação) | prontos, como Alteração — não há mais espécie retida por isso |
| óbitos reais validados contra o XSD | **398 de 398** |
| natimortos reais validados | **0** (a serventia não tem nenhum lavrado; a garantia é a letra do manual) |
| averbações reais validadas (Alteração) | **1 de 1** que passa pelo filtro do acervo (as outras 36 são de origem EOFICIO/ARQUIVO/IMPORTACAO) |

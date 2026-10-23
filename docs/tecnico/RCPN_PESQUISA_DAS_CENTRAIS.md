# O RCPN e as centrais: SIRC, CRC, IBGE, INFODIP e a Junta Militar

*29/08/2026 — pesquisa a pedido do oficial, antes de construir.*

> «Vamos primeiro buscar referências na internet sobre os principais sistemas
> que fornecem serviços para o RCPN e vamos inspirar nossas soluções neles,
> entre quais DeMaria, Consulticart, Extradigital e BookC. O E-Ofício tem todos
> serviços normais do RCPN, manda gerar o arquivo pra SIRC, CRC, IBGE, Junta
> Militar... Ideal que procuremos sobre a possibilidade de envio automático, mas
> não sendo possível, vamos na geração e exportação do arquivo correspondente.»

**Resposta curta: o envio automático é possível nas duas centrais que
importam** — SIRC e CRC —, e as duas têm manual técnico público, que está agora
guardado em `FONTES_EXTERNAS/`. O que falta em cada uma é o **certificado
digital**, e ele é decisão sua.

---

## Antes de tudo: uma correção do que eu disse ontem

Em 28/08 eu escrevi, e ficou registrado no `CLAUDE.md`, que **«SIRC, CRC e DNV —
aqui não há o que medir: o acervo não tem tabela de nenhuma das três»**.

**Estava errado, e pelo mesmo motivo de sempre: procurei TABELAS.** As três
estão no acervo, como **colunas**:

| onde | o quê | quantas |
|---|---|---|
| `tbRegistroNascimento.strDeclaracaoNascidoVivo` | o número da **DNV** | 61 de 193 |
| `tbRegistroNascimento.bitDNVInexistente` | a marca de que não há DNV | 193 de 193 |
| `tbRCPN_LocalNascimento.strWScrc` | o de-para do local de nascimento **para a CRC** | 5 de 5 |
| `tbRCTO_TipoLocalObito.strDescricaoCRC` | as descrições de local de óbito **da CRC** | 9 de 9 |
| `tbPropriedadeRCPN.strPathIBGE` | a pasta da remessa do IBGE | 1 |

E o óbito traz **tudo o que o SIRC pede**, que eu também não tinha visto:

| coluna | preenchidas |
|---|---|
| `strNumeroDeclaracaoObito` (a DO) | **31 de 31** |
| `strCPF` | **31 de 31** |
| `bitEleitor` | **31 de 31** |
| `bitPossuiBens` | **31 de 31** |
| `strTituloEleitor` | 18 de 31 |
| `strBeneficioSocial` (o NB do INSS) | 0 de 31 |

> **Quinta vez que este projeto aprende a mesma coisa.** Já aconteceu com o
> `codigoAto` dentro do `memJson`, com os contadores em `tbPropriedadeRCPN`, com
> o `intCodigoIBGE` do local de nascimento e com o `strTipoMorte`. **Não achar a
> tabela que procurei não prova que o dado não existe — prova que procurei pelo
> nome errado.** O que eu medi ontem foram os ARQUIVOS em disco; o dado estava
> no banco o tempo todo.

---

## 1. SIRC — e o envio automático EXISTE

**Fonte:** manual oficial *SIRC – Recomendações Técnicas*, 121 páginas, da
Dataprev, baixado de `sirc.gov.br` e guardado em
`FONTES_EXTERNAS/SIRC_manual_recomendacoes_tecnicas.pdf`.

### Os três caminhos, e o manual os separa

| caminho | como | o que exige |
|---|---|---|
| **SIRC Web** | o operador entra em `https://sirc.dataprev.gov.br` e sobe o arquivo | navegador, certificado do usuário |
| **Web Service com senha** | o sistema da casa chama `https://sirc.dataprev.gov.br/SircWs/Movimento` | usuário e senha |
| **Web Service com certificado** | `https://sirc.dataprev.gov.br/SircWs/MovimentoCertificadoDigital` | **certificado A3 da ICP-Brasil** |

O WSDL do primeiro está em `.../SircWs/Movimento?wsdl`.

### Como funciona, na letra do manual

> «Na alternativa de transmissão de movimento da serventia por Web Service,
> **não há geração de arquivos**. […] Sistema próprio da serventia gera uma
> sequência de texto XML conforme layout especificado; localiza e chama
> remotamente (via Internet) ao Web Service do SIRC passando os parâmetros
> necessários.»

E ele **devolve a crítica registro a registro**:

> «[SIRC] Geração dos registros no histórico de transmissão e devolução via Web
> Service do relatório de transmissão no formato XML.»

### O que o certificado exige, e é o ponto caro

> «O certificado digital utilizado para transmissão deve ser do tipo **A3**, e
> deverá ter sido emitido por uma Autoridade Certificadora credenciada pela
> Infraestrutura de Chaves Públicas Brasileira — ICP-Brasil.»

Mais **WS-Security**, com o certificado no cabeçalho SOAP, **XML Signature** do
próprio pacote, e *timestamp* de segurança.

> **A3 quer dizer cartão ou token físico.** Um serviço que roda sozinho no
> servidor precisaria do token espetado na máquina — e é por isso que este é o
> ponto que exige a sua decisão, e não um detalhe técnico.

### O que mais o manual traz, e vale saber

- **Declaração de Inexistência de Movimento** por web service (versão 3.3) — o
  mês sem registro **também se declara**;
- **Cancelamento** tem XSD próprio (versão 3.4);
- os XSDs por tipo: `MovimentoNascimentoTO.xsd`, `MovimentoCasamentoTO.xsd`,
  `MovimentoObitoTO.xsd`;
- tabelas anexas: **CBO-CNIS** (profissões), **TB0400 – Pequenas Tabelas** (onde
  mora o estado civil), municípios;
- o arquivo do modelo «SIRC Carga» é **compactado e criptografado**;
- há **recibo** (Anexo IV) e **relatório de processamento** (Anexo V).

---

## 2. CRC Nacional — envio automático também existe, e é XML assinado

**Fonte:** *Manual de Carga da Central de Informações do Registro Civil Nacional
— CRC Nacional*, versão 2.6, 79 páginas, da ARPEN-SP, baixado de
`sistema.registrocivil.org.br` e guardado em
`FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`.

### Os dois modelos, na letra do manual

> «**Modelo Carga**: […] o usuário do cartório acessará o sistema da CRC,
> utilizando o seu certificado digital e-CPF, e no campo específico fará upload
> do arquivo XML. **Este arquivo não será necessário estar assinado.**»
>
> «**Modelo Web Service**: […] o sistema próprio do cartório chamará um serviço
> disponibilizado pela CRC. O arquivo XML **precisará estar assinado
> digitalmente**, utilizando o seu certificado digital e-CPF e ser enviado
> formatado em **BASE 64**.»

Ambiente de teste: `https://wsh.registrocivil.org.br`.

### O layout está inteiro no manual

Raiz `<CARGAREGISTROS>`, com `<VERSAO>`, `<ACAO>`, `<CNS>`, e um dos três
movimentos:

| espécie | bloco | inclusão | alteração |
|---|---|---|---|
| nascimento | `<MOVIMENTONASCIMENTOTN>` | `<REGISTRONASCIMENTOINCLUSAO>` | `<REGISTRONASCIMENTOALTERACAO>` |
| casamento | `<MOVIMENTOCASAMENTOTC>` | `<REGISTROCASAMENTOINCLUSAO>` | `<REGISTROCASAMENTOALTERACAO>` |
| óbito | `<MOVIMENTOOBITOTO>` | `<REGISTROOBITOINCLUSAO>` | `<REGISTROOBITOALTERACAO>` |

**A ordem importa, e o manual a impõe**: *«deve-se formatar o XML primeiro com
as INCLUSÕES e depois com as ALTERAÇÕES em cada tipo de registro»*.

**E tag em branco não é tag ausente**: *«As tags que não forem enviadas, ou forem
em branco, serão incluídas como nulo ou "Ignorado(a)"»* — quem omitir um campo
está **afirmando que é ignorado**, e não deixando de afirmar.

### A CRC carrega os campos do SIRC

Na versão 2.0 o manual registra: *«Reformulação das cargas para o padrão XML e
**inclusão dos campos do SIRC**, de acordo com a Resolução nº 1/2015»*.

**Isso muda o desenho**: os dois envelopes compartilham quase todo o conteúdo, e
por isso o módulo deve ter **uma montagem só do fato registrado**, com dois
formatadores em cima — e não duas montagens paralelas que divergiriam no
primeiro conserto. É a lição do `_cobrar.html` e da `normalizar_nome`.

### Os catálogos externos que o XML cobra

| campo | fonte |
|---|---|
| `<CODIGOIBGEMUNNASCIMENTO>` e afins | tabela DTB do IBGE — **e esta casa já a tem**: `ib_municipios`, 5.570 municípios |
| `<PAISNASCIMENTO>`, `<NACIONALIDADE>` | padrão **M49 da ONU** |
| `<CODIGOOCUPACAOSDC>` | **CBO** do Ministério do Trabalho |
| `<CORPELE>` | BRANCA, PRETA, PARDA, AMARELA, INDIGENA, IGNORADA |
| `<TIPO_DOC>`, `<CODIGOORGAOEMISSOR>` | Anexos I e II do manual |
| `<CODIGOMOTIVOALTERACAO>` | Anexo III |

E há a regra do documento: *«A preferência de envio é sempre pelo CPF, somente
deverá ser enviado outro documento se não existir o CPF»* — o que casa com a
regra desta casa de que **o documento vem antes do nome**.

### O número do benefício do INSS

> «deve ser representado por um campo numérico de dez dígitos, sendo o último
> número um dígito verificador calculado a partir do módulo 11. […] Este número
> é de grande valia para **impedir o recebimento indevido de pagamentos feitos
> pelo INSS**.»

Medido nesta casa: `strBeneficioSocial` está **vazio nos 31 óbitos**. É campo
que o balcão precisa passar a perguntar.

---

## 3. A matrícula de 32 dígitos — e agora sei POR QUE ela não fecha

O manual da CRC exige `<MATRICULA>` com *«Somente 32 dígitos — Cálculo do dígito
verificador da Matrícula **Anexo IV**»*.

Fui ao Anexo IV: **ele é uma imagem**, sem texto extraível. E a busca na web
explica o resto — o portal do SIRC diz que o dígito

> «é formado automaticamente por meio do **programa que pode ser baixado
> gratuitamente** pelos Srs. Registradores Civis […] por meio do endereço
> www.cnj.jus.br/corregedoria/».

**O algoritmo não é publicado: o CNJ distribui um programa.** Isso encerra uma
pendência antiga deste projeto com uma resposta melhor que «não consegui»: não é
falha de medição, **é especificação não pública**.

E a estrutura que este projeto já tinha medido **está certa** — a página do SIRC
publica uma versão simplificada que junta CNS e acervo num bloco de 8, e as 244
matrículas reais desta casa desmentem:

```
000000  01   55   2022  1   00022  291  0019068  77
CNS(6) ac(2) tp(2) ano(4) T(1) livro(5) fl(3) termo(7) DV(2)
```

`000000` nos 244; `01` nos 244; `55` nos 244.

**Testei outra vez, com o esquema que faltava** — os dois dígitos em
**sequência** (o segundo calculado sobre os 31, incluindo o primeiro), quatro
conjuntos de pesos e as duas convenções de resto 10: **7 acertos em 244**. E o
ISO 7064 MOD 97-10, que é a conta do CNM do Registro de Imóveis: **0 de 244**.
Nível de acaso, outra vez — o que confirma que não há o que deduzir.

> O teste que fica vermelho se alguém escrever a função que gere a matrícula
> **continua valendo**, e agora com o motivo documentado.

---

## 4. IBGE — já está feito

`ibge_geracao.py` monta as três linhas do trimestre e foi conferido **posição
por posição** contra os arquivos que esta casa mandou de verdade: as 2 linhas de
casamento saem **byte a byte iguais**, 8 das 13 de óbito, e as 28 de nascimento
batem em tudo menos dois campos. Ver `REMESSA_IBGE_CONFERIDA.md`.

Nada a pesquisar aqui — o que falta é rodar.

---

## 5. INFODIP — a central que eu não conhecia, e ela é obrigatória

Foi o BookC que a revelou: ele lista **nove centrais**, e uma delas é o INFODIP.

**INFODIP** é o *Sistema de Informações de Óbitos e Direitos Políticos*, do TSE.
Segundo os Tribunais Regionais Eleitorais, ele é

> «o meio **oficial** de remessa das comunicações de **óbito, conscrição,
> conclusão do serviço militar obrigatório**, inelegibilidade, suspensão e
> restabelecimento de direitos políticos à Justiça Eleitoral»,

e **pode e deve ser utilizado pelos Cartórios de Registro Civil de Pessoas
Naturais**. Base normativa: **Resolução Conjunta CNJ/TSE nº 6, de 21/05/2020**.

O acesso não é automático: preenche-se um formulário cadastral, assina-se,
digitaliza-se e envia-se ao TRE; **usuário e senha voltam por e-mail em até 3
dias úteis**. É passo do oficial, e não meu.

Medido nesta casa: `bitEleitor` está preenchido nos **31 de 31** óbitos, e
`strTituloEleitor` em **18**. O dado existe.

---

## 6. Junta Militar — a obrigação mais esquecida, e há três casos de 2026

A base é a **Lei 4.375/1964 (Lei do Serviço Militar)**:

> «Os oficiais do Registro Civil deverão remeter, **mensalmente**, às
> respectivas **Circunscrições de Recrutamento**, relações, em modelos
> regulamentares, dos **óbitos de nacionais do sexo masculino, de dezessete a
> quarenta e cinco anos de idade, inclusive**, registrados no **mês anterior**.»

**Medido no acervo desta casa** — dos 31 óbitos, **quatro** caem na regra:

| nome | idade | óbito |
|---|---|---|
| PESSOA EXEMPLO | 22 | 18/04/2023 |
| PESSOA EXEMPLO | 26 | 31/05/2026 |
| PESSOA EXEMPLO | 22 | 01/06/2026 |
| PESSOA EXEMPLO | 20 | 17/07/2026 |

**Três são de 2026.** É obrigação mensal, e nada no sistema a acompanha.

> **É o mesmo tipo de prazo do SIGEF que a retificação acabou de ganhar**: uma
> obrigação **da serventia**, que nasce depois do ato, que ninguém de fora
> cobra, e que por isso se perde. A diferença é que esta **se repete todo mês**,
> inclusive nos meses em que não há nenhum óbito na faixa — e aí a relação vai
> vazia, como a declaração de inexistência do SIRC.

---

## 7. O que os quatro sistemas fazem — e o que se aprende deles

| sistema | onde | o que se viu |
|---|---|---|
| **DeMaria** | nacional, **mais de 700** serventias, três décadas | O RCPN dele *«integrou a nova central de comunicações, o SIRC, que gera os dados necessários para repasse ao INSS e ao IBGE»* e faz *«a elaboração de certidões em XML para upload na CRC Nacional»*. Tem **controle do processo de habilitação de casamento** como recurso próprio — que é o que esta casa construiu em 27/08. |
| **Consulticart** | Nordeste, mais de uma década | Vende **ecossistema integrado**: os módulos conversam nativamente entre si. É o argumento de venda deles, e é o que este projeto já é por construção — um banco só, um núcleo só. |
| **Extradigital** | Florianópolis/SC | Única credenciada em SC pela **AC Notarial** para habilitar cartórios em certificação digital. Tem página própria de **CRC — Registro Civil**. Mostra que a certificação digital costuma vir de um credenciador local. |
| **BookC** | Maranhão | **«O 1º sistema homologado com o selo eletrônico no Maranhão»** — o mesmo selador desta casa. Lista **nove centrais**: CRC Nacional, CRA, CENPROT, CENSEC, IBGE, SIRC, **INFODIP**, DOI e «Cartórios Maranhão». |

### O que este projeto tira daí, concretamente

**A lista de nove centrais do BookC é uma lista de conferência**, e ela mostra
onde estamos:

| central | como estamos |
|---|---|
| CENSEC | ligada (`notas_censec.py`) |
| DOI | **feita em 28/08** — arquivo único da serventia, das duas atribuições |
| CRA / CENPROT | Protesto medido e construído; o XML do CENPROT medido em 903 arquivos |
| IBGE | **gerada e conferida** contra os arquivos reais |
| SIRC | **a construir** — e o envio automático é possível |
| CRC | **a construir** — e o envio automático é possível |
| INFODIP | **a construir**; o cadastro é passo do oficial |
| «Cartórios Maranhão» | é o selador do TJMA, já ligado |

**Falta uma que o BookC não lista e a lei cobra: a Junta Militar.**

---

## O que eu proponho construir, nesta ordem

1. **A geração dos arquivos, antes do envio.** É o que você disse — *«não sendo
   possível, vamos na geração e exportação»* — e é também o caminho seguro: um
   arquivo que se pode conferir na tela antes de sair vale mais que um envio
   automático que ninguém viu. O envio entra depois, por cima da mesma
   montagem.
2. **Uma montagem só do fato, dois formatadores.** SIRC e CRC pedem quase o
   mesmo conteúdo — o manual da CRC diz isso na cara, ao registrar a «inclusão
   dos campos do SIRC». Duas montagens paralelas divergiriam no primeiro
   conserto.
3. **A relação da Junta Militar**, que é a mais simples e a mais atrasada: mês,
   homens de 17 a 45, óbitos do mês anterior. Três casos de 2026 esperando.
4. **O INFODIP**, depois de você fazer o cadastro no TRE.
5. **O envio automático**, quando houver certificado — e aí é decisão sua, porque
   o SIRC exige **A3**, que é token físico espetado na máquina.

### E o que eu não vou fazer

**Não vou gerar a matrícula de 32 dígitos.** O algoritmo não é público, o CNJ
distribui um programa, e 244 amostras contra tudo o que é padrão dão nível de
acaso. O campo continua sendo recebido, e o teste que impede alguém de escrever
a função continua vermelho se tentarem.

**Não vou inventar layout.** Onde o manual não disser, o campo fica `A CONFERIR`
e a pergunta vai para você ou para a central.

---

## As fontes

Os dois manuais estão guardados em `FONTES_EXTERNAS/`, **fora da pasta
empacotada** — juntos dão 4 MB, e não faz sentido carregá-los em toda
atualização. O texto extraído de cada um está ao lado, em `.txt`, que é o que se
lê e se procura.

- [SIRC via WebService](https://www.sirc.gov.br/sirc-via-webservice/) e o
  [manual de recomendações técnicas](https://sirc.gov.br/wp-content/uploads/manual_sirc_recomendacoes_tecnicas.pdf)
- [Manual de carga da CRC Nacional, v2.6](https://sistema.registrocivil.org.br/manuais/carga_registros_webservice_v2.6.pdf)
- [Matrícula e tipos de livro — guia SIRC](https://www.sirc.gov.br/guias/guia-sirc-cartorios/disposicoes-gerais/matricula-e-tipos-de-livro-de-registro/)
- [INFODIP — TRE-MA](https://www.tre-ma.jus.br/servicos-judiciais/mais-servicos/sistema-de-informacoes-de-direitos-politicos-infodip)
  e a [Resolução Conjunta nº 6/2020](https://atos.cnj.jus.br/atos/detalhar/3328)
- [Lei 4.375/1964 — Lei do Serviço Militar](https://www.planalto.gov.br/ccivil_03/leis/l4375.htm)
- [DeMaria](https://demaria.com.br/) · [ConsultiCart](https://consulticart.com.br/sistemas/)
  · [Extradigital — CRC Registro Civil](http://extradigital.com.br/site/sistemas-2/crc-registro-civil/)
  · [BookC](https://sistemabookcartorios.com/)

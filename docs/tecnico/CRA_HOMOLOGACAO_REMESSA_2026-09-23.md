# CRA-MA: primeira remessa real da homologação, recebida e medida

Data da medição: 23/09/2026. Versão na medição: 3.6.177; na publicação da
documentação, a fonte e a instalação estavam em 3.6.178, e os quatro módulos
`cra21_api.py`, `cra21_web.py`, `protesto_arquivo.py` e
`protesto_remessa.py` tinham SHA-256 iguais entre fonte e instalação. Escopo: **somente
homologação**, sem apontamento, sem importação no banco, sem confirmação, sem
retorno, sem selo e sem qualquer chamada à produção.

Este documento não contém nomes, números de títulos, CPF/CNPJ ou endereços.
A resposta integral, que pode conter dados pessoais, está preservada em pasta
privada no servidor. A Ajuda e o Agente podem indexar **este relatório**, mas
não devem indexar a resposta bruta.

## O que foi feito, exatamente

1. Confirmada a credencial de homologação sem ler nem exibir a senha. A
   operação segura `BuscarApresentante` respondeu (17.595 caracteres).
2. Às 13:37:01 de 23/09/2026, feita **uma** chamada SOAP `RemessaPendente`
   à CRA-MA em **HOMOLOGACAO**, com `userArq=B2372309.261` e
   `downloadImagem=2` (sem baixar imagens). Retentativas automáticas: **zero**.
   A chamada pode ter marcado as remessas como baixadas na CRA; não a repetir
   só para conferir o resultado.
3. Guardado o envelope SOAP completo e o texto de `<return>` em
   `C:\ProgramData\CartorioGestao\arquivos\cra_homologacao_20260923\`.
   A pasta tem ACL explícita: somente `SYSTEM`, `Administradores` e
   `SERVIDOR\usuario` têm acesso. Os nomes dos arquivos começam por
   `cra_homologacao_pendentes_20260923_133701`.
4. SHA-256 do SOAP: `a04be54a135bffbf8417e253bf0791d9042a2b0b4a16d8348903a8cf7715af58`
   (43.263 bytes). SHA-256 do `<return>`: `17cc397a84c66998858355d6ddb956c9bc106ae8878ddd4a83b66d078bdafc32`
   (42.487 bytes). O arquivo `.metadata.json` privado repete operação, hora,
   tamanho e hashes, sem credencial.
5. Lida a estrutura do retorno e feita conferência **somente de leitura**,
   contra o banco instalado. `pt_remessas` continuou com **0** linhas.

**Atenção ao nome:** `B2372309.261` foi o `userArq` solicitado e reapareceu
em `<nome_arquivo>` da resposta. Os três cabeçalhos têm data de movimento
**16/09/2026**, não 23/09. Não se deve supor que `<nome_arquivo>` identifique
sozinho a origem de cada lote; ele pode refletir o nome informado na chamada.

## Formato efetivamente recebido

O `<return>` é um **XML de remessa**, não um TXT FEBRABAN de linhas com 600
posições. A raiz é `<remessa>`, seguida por `<nome_arquivo>` e três sequências
`<hd>`, dez `<tr>`, `<tl>`. Cada `<hd>` traz `h01` a `h17`; cada título
`<tr>` traz `t01` a `t52`; cada `<tl>` traz `t01` a `t08`.

As aspas delimitadoras da declaração e dos atributos vieram como `&quot;`.
Por isso, o texto de `<return>` **não abre diretamente** num parser XML
comum. A normalização de `&quot;` para `"` permitiu a leitura. Não houve
caractere Unicode de substituição (`�`) na resposta extraída. A rotina
`cra21_api.ler_resposta` hoje desfaz `&amp;`, `&lt;` e `&gt;`, mas **não**
`&quot;`. É um defeito de adaptação SOAP/XML identificado com esta resposta.
Não gravar uma versão normalizada sobre o original: o bruto é a prova do que
a CRA enviou.

O layout coincide, em nomes de atributos e ordem, com o [Layout de
Transmissão de Arquivo de Protesto da FEBRABAN](https://cmsarquivos.febraban.org.br/Arquivos/documentos/PDF/Layout%20Transmissao%20Protesto.pdf)
(remessa XML, `hd`/`tr`/`tl`). O [manual de Web Service para cartórios da
CRA21](https://manual.p21website.com.br/docs/cartorio/cartorios-webservice/metodos-e-parametros-do-web-service/)
também declara a troca de arquivos XML. A descrição antiga do projeto de
que a API devolveria diretamente o arquivo TXT de 600 posições está
**superada por esta medição**. O leitor de TXT continua útil para arquivos
legados, mas falta um adaptador XML próprio para a API.

### Mapa dos atributos do cabeçalho (`hd`)

| Atributo | Significado pelo layout FEBRABAN |
|---|---|
| h01 | Tipo de registro, constante `0` |
| h02 | Código do apresentante/portador |
| h03 | Nome do apresentante/portador |
| h04 | Data do movimento, `DDMMAAAA` |
| h05 | Remetente da transação |
| h06 | Destinatário da transação |
| h07 | Tipo da transação |
| h08 | Número sequencial da remessa |
| h09 | Quantidade de registros declarada |
| h10 | Quantidade de títulos declarada |
| h11 | Quantidade de indicações |
| h12 | Quantidade de originais |
| h13 | Agência centralizadora |
| h14 | Versão do layout |
| h15 | Código do município da praça de pagamento |
| h16 | Complemento do registro |
| h17 | Sequencial do registro no arquivo |

### Mapa dos atributos do título (`tr`)

| Atributo | Significado pelo layout FEBRABAN |
|---|---|
| t01 | Tipo de registro, constante `1` |
| t02 | Código do apresentante |
| t03 | Agência/código do cedente |
| t04 | Nome do cedente/favorecido |
| t05 | Nome do sacador/vendedor |
| t06 | Documento do sacador |
| t07 | Endereço do sacador |
| t08 | CEP do sacador |
| t09 | Cidade do sacador |
| t10 | UF do sacador |
| t11 | Nosso número |
| t12 | Espécie do título |
| t13 | Número do título |
| t14 | Data de emissão |
| t15 | Data de vencimento |
| t16 | Tipo de moeda |
| t17 | Valor do título, em centavos |
| t18 | Saldo a protestar, em centavos |
| t19 | Praça de pagamento |
| t20 | Tipo de endosso |
| t21 | Aceite |
| t22 | Controle dos devedores |
| t23 | Nome do devedor |
| t24 | Tipo de documento do devedor (`001` CNPJ, `002` CPF) |
| t25 | Documento do devedor |
| t26 | Documento complementar do devedor |
| t27 | Endereço do devedor |
| t28 | CEP do devedor |
| t29 | Cidade do devedor |
| t30 | UF do devedor |
| t31 | Número do cartório |
| t32 | Número do protocolo do cartório |
| t33 | Tipo de ocorrência |
| t34 | Data do protocolo |
| t35 | Custas do cartório |
| t36 | Declaração do portador |
| t37 | Data da ocorrência |
| t38 | Código de irregularidade |
| t39 | Bairro do devedor |
| t40 | Custas do distribuidor |
| t41 | Registro de distribuição |
| t42 | Demais despesas |
| t43 | Número da operação do banco |
| t44 | Número do contrato do banco |
| t45 | Parcela do contrato |
| t46 | Tipo de letra de câmbio |
| t47 | Complemento do código de irregularidade |
| t48 | Protesto por motivo de falência |
| t49 | Instrumento de protesto |
| t50 | Demais despesas (Sedex/CPMF no layout histórico) |
| t51 | Complemento do registro; pode ter outro uso em fluxos posteriores |
| t52 | Número sequencial do registro |

### Mapa dos atributos do trailer (`tl`)

| Atributo | Significado pelo layout FEBRABAN |
|---|---|
| t01 | Tipo de registro, constante `9` |
| t02 | Código do apresentante |
| t03 | Nome do apresentante |
| t04 | Data do movimento |
| t05 | Somatório de segurança/quantidade declarada |
| t06 | Somatório dos saldos `tr.t18` |
| t07 | Complemento do registro |
| t08 | Sequencial do registro |

## Resultado da conferência desta resposta

| Lote | Apresentante | Data `h04` | Títulos | Saldo `t18` | Contagens, soma e sequenciais |
|---|---:|---|---:|---:|---|
| 1 | 237 | 16/09/2026 | 10 | R$ 206,19 | conferem |
| 2 | 237 | 16/09/2026 | 10 | R$ 203,68 | conferem |
| 3 | 237 | 16/09/2026 | 10 | R$ 206,64 | conferem |
| **Total** | | | **30** | **R$ 616,51** | |

Nos três lotes, `h14=043`, `h15=2198765`, `h10=10` e `tl.t06` bate
exatamente com a soma de `tr.t18`. A sequência dos registros fecha; não há
datas inválidas em `t14`/`t15` nem repetição da combinação apresentante +
nosso número + número do título dentro da resposta. O conjunto contém 23
espécies de título; são 19 identificações de devedor do tipo CPF e 11 do tipo
CNPJ. Esses números são **dados de homologação**, não movimento da serventia.

Como ensaio, os atributos foram projetados **apenas em memória** nas posições
de 600 caracteres e submetidos a `protesto_remessa.conferir`, com conexão
SQLite `mode=ro`. Resultado: **3 lotes, 30 aceitos, 0 recusados, 0 avisos
de duplicidade**. Surgiram 3 alertas sobre a contagem do trailer, um por
lote. São **falsos positivos do adaptador provisório**: na resposta XML,
`tl.t05=30` corresponde ao somatório de segurança
`h09+h10+h11+h12=10+10+2+8` (ou `10+10+0+10`, etc.); o leitor TXT antigo o
trata como número de linhas e compara com 12. Um adaptador de produção deve
validar a semântica XML própria, sem silenciar os alertas verdadeiros do TXT.

## O que pode avançar e o que continua bloqueado

**Pode avançar agora:** implementar e testar um leitor de remessa XML da
CRA21 com desescapamento correto da resposta SOAP, preservação do XML bruto,
separação de `hd`/`tr`/`tl`, validações de contagem/soma/sequência,
pré-visualização sem escrita, chave idempotente por hash do conteúdo e
ambiente, e tradução explícita dos campos para o vocabulário do Protesto.
O fluxo existente `protesto_remessa.conferir`/`receber` fornece as regras de
domínio, mas **não** deve receber o XML cru nem uma conversão provisória
sem revisão do trailer. Criar testes com fixture **sintética ou anonimizada**;
o arquivo bruto privado não pertence ao repositório nem ao pacote `.cgu`.

**Não fazer automaticamente:** protocolar/apontar, emitir aviso, selar,
cobrar, enviar `Confirmacao` ou `Retorno`, nem trocar a configuração para
produção. O contrato de `userDados` para essas duas operações ainda precisa
ser demonstrado num teste próprio. A resposta recebida ajuda a montar o XML
de confirmação, mas **não prova** que a CRA o aceitará.

**Não repetir a baixa para medir formato.** A evidência está guardada com
hash; uma nova chamada pode trazer resposta diferente ou marcar novamente
arquivos na central. Para novo teste, usar uma remessa de homologação criada
de propósito e registrar o nome/data acordados com a CRA.

Ferramentas locais desta medição:
`tools/baixar_remessa_cra_homologacao.py` (chamada única, sem retry) e
`tools/analisar_remessa_cra_homologacao.py` (somente leitura, saída agregada).
Nenhuma delas integra automaticamente o fluxo de produção.

## Avanço implementado em 24/09/2026 (ainda não instalado)

- `protesto_cra_xml.py` lê a estrutura XML efetivamente observada em
  `RemessaPendente`, confere largura de todos os atributos, datas, sequência,
  contagens e saldo dos trailers, e projeta linhas de 600 posições **apenas
  em memória** para reaproveitar a validação de títulos existente.
- A tela **Remessa da CRA** aceita XML para **conferência somente leitura**.
  Não mostra formulário de recebimento para XML; a rota de recebimento também
  recusa XML diretamente. Os falsos alertas do trailer TXT são removidos só
  depois da validação própria e estrita do XML.
- A camada SOAP não faz nova tentativa automática para operações de download
  (`Remessa`, `RemessaPendente` e correlatas), pois a CRA pode ter marcado o
  arquivo como baixado mesmo quando a conexão local falhou. A mensagem de
  erro passou a declarar essa incerteza.
- Testes sintéticos de leitura XML, transporte da CRA e migração: 33 passaram.
  Compilação Python e análise de sintaxe dos três templates: passaram. Os
  testes da aplicação web não rodaram neste ambiente: o `lxml` do venv local
  contém binários para Python 3.11, mas o interpretador disponível para teste
  é de outra versão. Não considerar a tela homologada sem esse teste.

O leitor agora também produz um hash por lote a partir dos atributos XML
originais, separa a futura chave de idempotência por ambiente e recusa lote
idêntico repetido dentro do arquivo. O código-fonte já prepara coluna e índice
`UNIQUE` por migração aditiva, mas a instalação em uso não foi atualizada e
nenhum fluxo persiste essa chave ainda. O plano operacional está detalhado em
`CRA_XML_INTEGRACAO_ESTADO_2026-09-24.md`.

**Permanece bloqueado:** recebimento/importação de XML na base real, criação
de confirmação, envio de `Confirmacao` e ativação em produção. Além dos testes
da tela no runtime correto, falta validar com a CRA o contrato do retorno de
confirmação e a chave de idempotência por ambiente + hash + identificação do
lote. A remessa privada de homologação não foi reapresentada nem importada.

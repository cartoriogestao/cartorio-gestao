# Referências para melhorar o sistema — E-Ofício e BookC

**Levantamento de 13/08/2026.** Serventia do Ofício Único de Cidade Exemplo/MA — CNS 000000.

Dois sistemas serviram de referência: o **E-Ofício / Automação Cartorária MA**, que está instalado
e em uso na serventia (`C:\ARPNET\C11`, banco `bdCartorio` no SQL Server), e o **BookC**, sistema
maranhense de gestão de cartórios. O E-Ofício foi lido por dentro — pastas, arquivo de
configuração e esquema completo das tabelas de RI. O BookC foi lido só pelo site do fabricante.

---

## 1. O que já foi trazido hoje

### 1.1 As 128 naturezas do SAUIN

A tabela `tbRI_NaturezaTitulo_SAUIN` do E-Ofício tem **128 naturezas de título, todas ativas**.
Não é lista de fabricante: é o vocabulário que o **selo eletrônico do Maranhão** reconhece.

O nosso sistema pedia a natureza como texto livre. Isso significa que o mesmo ato podia sair como
"Compra e venda", "compra/venda" ou "C.V." — e nenhum casa com o selo. Agora a lista do SAUIN
aparece como sugestão nas telas de lavratura e de protocolo, com o código preservado.

Classifiquei as 128 em **55 registros e 73 averbações**, pelo nome, com cinco exceções à mão —
penhora, arresto, sequestro, renúncia de usufruto e indisponibilidade. A tabela de origem não diz
qual é qual; a classificação é útil, não é dogma.

De quebra, 33 dessas naturezas agora mapeiam direto para a operação imobiliária da CTP. Antes
a CTP tinha de adivinhar pelo texto; agora, quando a natureza vem da lista, é certeza — e a tela
diz de onde veio o palpite.

### 1.2 O tipo do imóvel — um dado que estava lá e nós jogamos fora

`tbRI.intTipoImovel` está preenchido em **1.689 das 1.721 matrículas** do E-Ofício. A nossa carga
não trouxe. Consequência prática: as 1.699 matrículas do nosso banco estão com o tipo em branco, e
por isso o **Indicador Real do ONR** sai com o tipo genérico e a **CTP** sairia com
"Terreno/fração" para tudo.

O importador foi corrigido, e existe agora o `COMPLETAR_TIPO_IMOVEL.cmd` para consertar o que já
está no banco sem refazer a importação. Testei contra uma cópia do banco de produção: **casou
1.699 de 1.699**, ficando 1.362 Fazenda/Sítio/Chácara, 293 Terreno/fração, 32 Casa, 9 Outros,
2 Prédio residencial e 1 Sala/Conjunto. Nada além desse campo é tocado.

A mesma tabela do E-Ofício traz `intCodigoDOI` ao lado de `onr_id` — e os códigos batem
exatamente com os que eu tinha posto na CTP (67 Casa, 65 Apartamento, 15 Loja, 71 Terreno,
69 Fazenda, 89 Outros). Confirmação independente, de graça.

### 1.3 A qualificação das partes — o achado mais valioso, e ainda não resolvido

`tbRI_Partes.intQualifica` está preenchido nas **4.042 partes**, com códigos concentrados em
1 (1.991 vezes), 8 (956), 47 (494), 10103 (203), 29 (87) e 57 (85). A nossa carga ignorou o campo
e gravou **todo mundo como "proprietário"**.

Isso é o que hoje impede três coisas ao mesmo tempo:

- o **Indicador Pessoal do ONR** sai sem papel;
- a **CTP** não pode incluir ato nenhum do acervo, porque exige alienante e adquirente separados;
- a **cadeia dominial** na ficha não mostra quem transmitiu para quem.

O domínio desses códigos não está nas tabelas `tbRI_*` — deve estar em `tbTabelas`, a tabela
genérica de domínios do E-Ofício. Criei o `EXPORTAR_QUALIFICACAO.cmd`, que só lê, exporta
`tbTabelas` inteira e a distribuição real dos códigos com um nome de exemplo ao lado, para
conferir o encaixe. Rodando isso, dá para recuperar o papel das 4.042 partes de uma vez.

---

## 2. O que o E-Ofício tem e o nosso sistema não

### 2.1 Livros e controles

| No E-Ofício | O que é | Nós |
|---|---|---|
| `tbRI_RecepcaoTitulo` + `tbRI_Controle_LivroRecepcao` | **Livro de Recepção de Títulos** — apresentante, natureza formal, data de apresentação, de devolução e de entrega | não temos |
| `tbRI_Controle_LivroA` | Controle do Livro 2: ordem inicial e final, páginas, datas, **termo de encerramento** | não temos |
| `tbRI_Controle_LivroIndicadorReal` / `...IndicadorPessoal` | mesmo controle para os Livros 4 e 5 | não temos |
| `tbRI_LivroAquisicaoEstrangeiro` | o livro do art. 424, VI, do Código TJMA | não temos |
| `strRA_livro`, `strRA_pi`, `strRA_pf`, `strRA_data` em `tbRI` | vínculo da matrícula com o **Registro Auxiliar** (Livro 3) | não temos o Livro 3 |

O ponto comum: **nós não temos termo de abertura nem de encerramento de livro nenhum**. O sistema
guarda os atos, mas não fecha o livro. Numa correição isso aparece.

### 2.2 Procedimentos especiais com cobrança em fases

`tbRI_TipoProcedimentoEspecial` + `tbRI_ProcedimentoEspecialPG` + `tbRI_CobrancaProcedimentoFase`
são três tabelas para uma coisa só: **procedimento que se cobra por etapa**, com percentual
inicial e percentual complementar, valor base, valor cobrado e data de cada cobrança.

É exatamente a estrutura que faltaria para usucapião extrajudicial, retificação administrativa,
adjudicação compulsória e REURB — os procedimentos que apontei como faltando na revisão normativa.
O E-Ofício já tinha resolvido o problema do dinheiro; nós ainda não temos nem o procedimento.

### 2.3 Campos que existem lá e faltam aqui

- **`bitFronteira`** — imóvel em faixa de fronteira, que exige assentimento do Conselho de Defesa
  Nacional. Está vazio no acervo, mas o campo existir é o que faz alguém lembrar de perguntar.
- **`bitEstrangeiro`** — aquisição por estrangeiro (Lei 5.709/1971). Também vazio, e também
  necessário: sem ele não há como montar o relatório trimestral ao INCRA e à Corregedoria.
- **`strConfrontacao_N/S/L/O`** — confrontações **por rumo**, em quatro campos separados. Nós
  guardamos tudo num texto só. Separado é melhor para conferir sobreposição.
- **`id_SituacaoMatricula`** — vocabulário de situação: Ativa, Anulada, Encerrada, Cancelada.
  Nós temos só ativa/encerrada.
- **`intNumeroChaveCX`** no protocolo — o número da gaveta onde está o título físico. Miúdo, mas
  é o tipo de coisa que faz o balcão andar.
- **`dtmPrevisaoEntrega`** — a data prometida ao apresentante. Nós temos o prazo legal, não a
  promessa feita ao balcão.
- **`bitReurb`, `bitGratuito`, `intPercentual_Concedido`, `strMotivoIsencao`,
  `bitSubstitutoTributario`, `bitDepositoPrevio`** — todo o tratamento de gratuidade, REURB e
  depósito prévio. Nós não temos nada disso.
- **`bitPPE`** em `tbParte` — pessoa politicamente exposta. É a marca que o PLD/FTP exige, e o
  Código TJMA manda verificar no SISCOAF. A correição já cobrou SISCOAF desta serventia.
- **`tbRI_Prop_Ficha_ONR`** — margens e tipo de papel para **imprimir na ficha pré-impressa**. A
  serventia tem ficha física; nós imprimimos página inteira.

### 2.4 Uma leitura das pastas que vale registrar

Dentro de `C:\ARPNET\C11` existem pastas **`CENSEC`, `SINTER`, `CRC` e `Remessa` — todas vazias**.
O E-Ofício previu esses canais e eles nunca foram usados. Combina com o que a correição apontou
sobre DOI e SISCOAF: não é falta de sistema, é falta de rotina. Vale como aviso para nós — criar
a tela não basta; o que fecha a pendência é o comprovante mensal.

Já `ONR` e `IPDigital` têm conteúdo de verdade (arquivos `.p7s` assinados, indicadores enviados),
e foi de lá que veio o formato real do ONR que o nosso módulo usa.

O `C11.INI` confirmou, de passagem, o **código IBGE 2198765** que eu tinha posto na CTP.

---

## 3. O que o BookC mostra

O BookC se apresenta como o primeiro sistema homologado com o selo eletrônico no Maranhão. Do
que está publicado no site, o que interessa:

**Módulos que ele tem e nós não:** Arquivamento Eletrônico, Atendimento, **Fluxo de Trabalho** e
**Fluxo de Caixa**. O fluxo de trabalho é o que falta para o título andar entre pessoas —
recepção, qualificação, lavratura, conferência, entrega — com dono e prazo em cada etapa.

**No Registro de Imóveis** ele anuncia os **cinco livros** (1 Protocolo, 2 Registro Geral,
**3 Registro Auxiliar**, 4 Indicador Real, 5 Indicador Pessoal) e a **geração do arquivo de carga
da DOI**. Confirma, de outro ângulo, as duas lacunas que a revisão normativa já tinha apontado:
o Livro 3 e as remessas.

**Centrais com que ele conversa:** CRC, CRA, CENPROT, CENSEC, IBGE, SIRC, INFODIP, DOI e
**"Cartórios Maranhão — Central Única de Serviços Eletrônicos Compartilhados"**.

Essa última é a novidade para a nossa lista. É uma central **estadual**, que não aparecia em
nenhum levantamento anterior meu. Vale descobrir o que ela exige do Registro de Imóveis antes de
supor que o ONR e a CENSEC cobrem tudo.

**Emissão de etiquetas** no RTD/RCPJ — miúdo, mas é o tipo de coisa que só quem trabalha no balcão
lembra de pedir.

---

## 4. O que vale trazer, em ordem

1. **Rodar o `EXPORTAR_QUALIFICACAO.cmd`** e recuperar o papel das 4.042 partes. Destrava ONR,
   CTP e cadeia dominial de uma vez só. É a maior relação benefício/esforço da lista.
2. **Rodar o `COMPLETAR_TIPO_IMOVEL.cmd`.** Já está pronto e testado.
3. **Termos de abertura e encerramento de livro**, para os Livros 1, 2, 4 e 5. É o que falta para
   o sistema fechar o que abre.
4. **Livro 3 — Registro Auxiliar**, e o vínculo da matrícula com ele. Já estava na revisão
   normativa; o BookC e o E-Ofício confirmam de dois lados.
5. **Livro de Recepção de Títulos.** Existe no E-Ofício e é o registro do que entrou sem prenotar.
6. **Marcas de fronteira, estrangeiro e pessoa politicamente exposta.** Três campos que valem por
   três obrigações: Conselho de Defesa Nacional, relatório trimestral ao INCRA e SISCOAF.
7. **Gratuidade, REURB e depósito prévio** no protocolo.
8. **Procedimentos especiais com cobrança em fases**, junto com os procedimentos em si.
9. **Fluxo de trabalho** — a ideia do BookC de o título ter dono e etapa.
10. **Averiguar a central "Cartórios Maranhão"** antes de fechar a lista de remessas.

---

## 5. O que não vale copiar

O E-Ofício guarda o texto do ato em **seis campos diferentes** — `memTeorFichaFormatado`,
`memTextoFicha`, `memRegistroImovel`, `memRegAnterior`, `memTexto` e `memCertidaoRegistro` — com
preenchimento desigual entre eles. Foi justamente isso que tornou a migração difícil e que gerou
metade dos erros que registrei no `APRENDIZADO_MIGRACAO_RI.md`. Nós temos um teor por ato, com
cadeia de hash. Fica como está.

Também não vale copiar a ausência de trilha: no E-Ofício o ato se edita. No nosso, não.

---

## 6. O que eu não conferi

- **Não abri o BookC.** Tudo o que está na seção 3 vem do site do fabricante, que é material de
  venda. Não vi tela, não vi arquivo gerado, não sei o que de fato funciona.
- **Não consultei o SQL Server agora** — o banco fica na máquina Windows e eu leio daqui um
  ambiente separado. Usei o esquema e as exportações que já estavam no Downloads, de hoje mais
  cedo. Os números de preenchimento vêm desses arquivos, não de consulta ao vivo.
- **O domínio da qualificação é hipótese.** Suponho que `intQualifica` aponte para `tbTabelas`
  porque é o padrão do sistema e não há outra candidata. Pode estar errado — o script de
  exportação existe justamente para descobrir.
- Não testei o `COMPLETAR_TIPO_IMOVEL.cmd` na máquina real, só a lógica dele contra uma cópia do
  banco de produção.

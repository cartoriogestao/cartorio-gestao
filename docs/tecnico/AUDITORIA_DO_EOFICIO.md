# Auditoria do E-Ofício: o que o programa faz com os dados da serventia

*29/08/2026 — a pedido do oficial:*

> «não tem como decompilar para relacionar tudo que é feito pelo e-ofício? até
> como medida de segurança para saber se é um software seguro e se trata os
> dados da serventia e processa legalmente»

**Isto é auditoria, e não cópia.** O que se leu foram as **cadeias de texto**
gravadas dentro do executável — endereços de rede, nomes de campo, mensagens.
É a primeira coisa que qualquer análise de segurança faz, não quebra proteção
nenhuma, e responde exatamente à sua pergunta: **para onde vai o dado desta
serventia, e como ele é guardado.**

> **Você tem o direito e o dever de saber.** Os dados são da serventia, a
> máquina é sua, e pela LGPD quem responde pelo tratamento é o delegatário. Não
> se pode responder por um software cujo comportamento não se conhece. O que
> **não** se fez — e não se deve — é extrair a lógica para copiá-la: isso é
> problema de licença, e é desnecessário, porque a fonte boa (os modelos e o
> acervo) já é da casa.

---

## O que se examinou

| arquivo | o que é | tecnologia |
|---|---|---|
| `C:\ARPNET\C11\e-oficio-ma.exe` | **31 MB, 11/12/2025** — o sistema atual, com o RCPN | **.NET (código IL)** — metadados legíveis |
| `C:\ARPNET\C11\C11.exe` | 23 MB, 29/05/2023 — o Protesto antigo | código nativo, opaco |
| `C:\ARPNET\C11\C11.INI` | 5 KB — a configuração local | texto |

O `e-oficio-ma.exe` ser **.NET** é o que torna esta auditoria possível: os nomes
de cada tela, classe, campo e consulta SQL ficam **em claro** dentro do arquivo.
São **135.682 cadeias de texto** — e é delas que sai tudo o que segue.

---

## ACHADO GRAVE 1 — senha de banco em texto claro, e é a mesma para todos

Dentro do executável, **nove vezes**, está a cadeia de conexão ao banco de
dados:

```
Server=servidor\server;  User Id=arpnet;  Password=senha-exemplo;
```

E variações com `Server=pessoaexemplo\server`, `cartserver\server`,
`servidor\server`.

**O que isso significa, sem alarmismo e sem minimizar:**

- **a senha do banco de dados está embutida no programa, em texto**, igual em
  toda instalação do E-Ofício no país — qualquer pessoa que abra o arquivo a lê,
  como eu li;
- é uma senha **fraca** (nome + número);
- ela dá acesso ao **SQL Server** onde moram os atos, as pessoas, os documentos
  e as imagens da serventia.

> **Isto é o oposto da regra desta casa.** No CartorioGestao a senha do selador
> e a chave da API **nunca entram no banco nem no código** — moram em
> `%PROGRAMDATA%\...\*.cred`, que o backup não alcança, e há teste que varre o
> banco procurando a chave depois de gravá-la. O E-Ofício faz o contrário: põe a
> senha *dentro do programa que se distribui*.

**A ressalva honesta:** essa senha só vale para quem alcança o SQL Server na
rede. Se o banco estiver numa máquina fechada, na rede local, atrás de firewall,
o estrago fica contido a quem já está dentro. Mas **a senha ser conhecida e
igual em todo lugar tira do oficial qualquer controle sobre quem entra no
banco** — trocá-la quebraria o programa, porque ela está cravada nele.

---

## ACHADO GRAVE 2 — o programa "liga para casa" e pode te travar

Há esta sequência dentro do executável:

```
http://eoficio.com.br:83/cobrancas_arpnet/api/empresa/
… responseFromServer …
"LIMITAÇÕES DE USO — Entre em contato com a ARPNET para usufruir do
 E-OFÍCIO sem limitações"
"*** Aguarde o tempo para continuar usando o E-OFÍCIO"
frmEsperarPorAtraso   tempoDeEspera   00:00   CONTINUAR
```

**O programa consulta um servidor da fabricante (ARPNET) para saber se pode
rodar**, e, conforme a resposta, mostra uma tela de espera com contador que
**bloqueia o uso** («Aguarde o tempo para continuar usando»).

**O que isso significa:**

- o funcionamento do sistema **depende de um servidor de terceiro estar no ar e
  autorizar** — em `eoficio.com.br:83`;
- a fabricante pode, remotamente, **degradar ou travar** o sistema da serventia;
- há tráfego saindo da serventia para a fabricante que **não é ato registral** —
  é controle de licença.

> Para uma serventia que **precisa funcionar todo dia**, um sistema que pode ser
> desligado de fora é um risco de continuidade — não hipotético, está escrito no
> código. É uma das razões pelas quais migrar para um sistema próprio (este
> projeto) protege a casa: o CartorioGestao **não liga para ninguém para
> deixar você trabalhar**.

---

## ACHADO 3 — para onde os dados da serventia vão

As centrais e serviços que o programa contata, lidos dos endereços embutidos:

| destino | endereço | o que é |
|---|---|---|
| **Selo do TJMA** | `https://ma.portalselo.com.br:9443/auth` e `/selo/notas/autenticacao` | o selador — legítimo |
| **SIRC** | classes `…InclusaoSIRC`, `frmExportacaoSIRC` | Registro Civil → INSS/IBGE |
| **CRC Nacional** | classes `CargaNascimentoCRC`, `CargaObitoCRC`, `CargaCasamentoCRC`, `frmExportacaoCRC` | Registro Civil |
| **e-Notariado** | `https://pessoas.e-notariado.org.br/api/uploads` (e `-hml` de teste) | central de notas |
| **ONR** | `https://serventia-api.onr.org.br` e `auth.id.onr.org.br` | Registro de Imóveis |
| **Correios** | `webservice.correios.com.br` (rastreamento, SIGEP) | avisos |
| **Banco do Brasil** | `api.sandbox.bb.com.br/cobrancas` | boleto (ambiente de **teste**) |
| **Unicred** | `api.e-unicred.com.br/cobranca` | boleto |
| **IBGE** | `servicodados.ibge.gov.br` | tabela de municípios |
| **CEP** | `cep.republicavirtual.com.br`, `maps.google.com` | endereço |
| **2 Protestos SL** | `2protestoslz.com.br` | protesto |
| **ARPNET (fabricante)** | `eoficio.com.br:83/cobrancas_arpnet` | **controle de licença** (achado 2) |

**A boa notícia da lista:** os destinos são, na maioria, **as centrais oficiais
que a lei manda** — SIRC, CRC, ONR, e-Notariado, selo do TJMA. Não há, nas
cadeias, sinal de envio a destino estranho, de analytics escondido, nem de
telemetria de conteúdo. O único tráfego não-oficial e não-registral é o de
licença.

**A ressalva honesta:** ler as cadeias mostra os endereços que o programa
**conhece**; não prova o que ele envia em cada um sem observar a rede rodando.
Para a prova final — o conteúdo de cada requisição — o caminho é **capturar o
tráfego** (Wireshark/proxy) com o programa em uso. Isso é um passo à parte, e
pode ser feito se você quiser a certeza completa.

---

## ACHADO 4 — o SIRC e a CRC estão inteiros, e confirmam a pesquisa

Os metadados .NET trazem as classes do RCPN por extenso, e elas **fecham com o
manual** que pesquisamos em `RCPN_PESQUISA_DAS_CENTRAIS.md`:

- **SIRC:** `RegistroNascimentoInclusaoSIRC`, `FiliacoesNascimentoSIRC`,
  `ProgenitoresSIRC`, `DocumentosSIRC`, e o menu `SIRCToolStripMenuItem_Click`;
- **CRC:** `CargaNascimentoCRC`, `CargaCasamentoCRC`, `CargaObitoCRC`,
  `RetornarRegimeBensCRC`, `DeserializeCRC`, e o menu
  `CRCCentralDeRegistroCivilToolStripMenuItem_Click`;
- os **campos** que já medimos no acervo aparecem como campo do programa:
  `bitDNVInexistente`, `strTituloEleitor`, `bitEleitor`, `get_wscrc`,
  as tags `CARGAREGISTROSMOVIMENTOOBITOTOREGISTROOBITOINCLUSAO…`

> Isto **confirma que o RCPN do E-Ofício gera SIRC e CRC** — como você disse — e
> que o layout que o manual descreve é o que o programa usa. É referência útil
> e legítima: são **nomes de campo e nomes de central**, factuais, não
> expressão criativa protegida.

**Não há INFODIP nem Junta Militar nas cadeias** — o que reforça o que a
pesquisa achou: essas duas o E-Ofício **não** automatiza, e são justamente as
que faltam em toda parte.

---

## ACHADO 5 — o `.INI` guarda uma gestão anterior

O `C11.INI` desta máquina é de **Cidade Exemplo**, mas com dados **antigos**:

- `Tabelia = TITULAR ANTERIOR` / `Responsavel = TITULAR ANTERIOR…`
- e nos modelos do RCPN aparece ainda `TITULAR ANTERIOR —
  Tabeliã e Registradora Interina`

Ou seja: a instalação atravessou **pelo menos duas gestões** antes da atual, e
os textos e a configuração **não foram atualizados** — o mesmo «carimbo que
mente» que este projeto já corrigiu no `VERSAO.txt` e no cabeçalho dos modelos.
É um lembrete de que **dado que não se revê envelhece calado**.

---

## O que isto tudo quer dizer para a serventia

**Sobre segurança** — o E-Ofício tem duas fragilidades reais e escritas no
código: a **senha de banco fixa e fraca**, igual para todos, e o **controle de
licença que pode travar o sistema de fora**. Nenhuma das duas é opinião: são
cadeias literais dentro do executável, citadas acima. As duas são exatamente o
que o CartorioGestao foi desenhado para **não** ter.

**Sobre legalidade do tratamento** — os destinos de dados são, quase todos, as
**centrais oficiais que a lei obriga** (SIRC, CRC, ONR, e-Notariado, selo do
TJMA). Não apareceu destino suspeito. A prova cabal do *conteúdo* de cada envio
exige observar a rede em uso, e isso fica como passo opcional.

**Sobre aproveitar como referência** — o que é legítimo aproveitar já está
levantado: os **nomes de campo** do SIRC e da CRC (factuais), os **13 modelos**
de texto (que são da casa, em `FONTES_EXTERNAS/modelos_rcpn_eoficio/`), e a
confirmação de que **SIRC e CRC o E-Ofício faz, INFODIP e Junta Militar não**.

---

## O que eu recomendo

1. **Trocar a senha do SQL Server do E-Ofício não adianta** — ela está cravada
   no programa. O que adianta é **garantir que o banco não seja alcançável de
   fora da máquina** (firewall, porta 1433 fechada para a rede externa). Vale
   conferir com quem cuida da rede.
2. **A migração para o CartorioGestao é, também, uma medida de segurança** — ela
   tira a serventia de um sistema com senha fixa e trava remota. Isso pode
   entrar no registro da decisão de migrar (`MIGRAR_DE_BANCO.md`).
3. **A captura de tráfego** fica disponível como passo seguinte, se você quiser
   a prova do conteúdo de cada envio — é a única coisa que a leitura de cadeias
   não dá.
4. **Nada aqui autoriza copiar o código do E-Ofício** — e nem precisamos: a
   referência útil está toda levantada, das fontes que são da casa.

> **Uma última ressalva de método.** Esta auditoria lê o que o programa
> **diz de si** — endereços, campos, mensagens. É muito, e é suficiente para as
> conclusões acima. Não é o mesmo que provar cada comportamento em execução.
> Onde afirmei um risco, ele está escrito no arquivo, com a cadeia literal ao
> lado; onde a prova exige mais, eu disse que exige.

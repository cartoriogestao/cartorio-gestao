# Como aderir ao Next Cloud SAS do ONR — o passo a passo

    «vamos seguir a modalidade b. processse, escreva, me ensine a usar.
     e como fica o indicador real?»               — o oficial, 04/09/2026

Este é o roteiro de uso. O que está **por trás** de cada decisão está em
`O_NEXT_CLOUD_SAS_DO_ONR.md`; aqui é o que fazer, na ordem.

---

## Primeiro, a sua pergunta: o indicador real

**São três coisas, e o Next Cloud SAS leva duas.**

| o quê | por onde vai | onde se faz no sistema |
|---|---|---|
| **Indicador Pessoal** (Livro 5) | Next Cloud SAS — banco *Firestore*, pelo programa **IPS** | *RI → Carga do Next Cloud SAS* |
| **Imagens das matrículas** (Livro 2) | Next Cloud SAS — *Bucket*, pelo programa **CSL2** | *RI → Carga do Next Cloud SAS* (só conferência) |
| **Indicador Real** | **não passa pelo Next Cloud SAS** — vai pela API, `POST /v1/indicador/real` | *RI → Central do ONR* |

**Aderir à modalidade (b) não desliga o indicador real.** Medido nos seis
documentos do ONR que estão na casa — o manual de integração 3.7 e os cinco
que ele cita —, a expressão «indicador real» aparece **zero vezes em todos**.

E o motivo é que são coisas de natureza diferente:

- o **Next Cloud SAS é armazenamento**: um balde de arquivos e um banco de
  pesquisa, que ficam do seu lado e que o ONR **lê** quando alguém pesquisa;
- o **indicador real é envio**: matrícula por matrícula, para o índice
  nacional, com fila e situação próprias — construído em 03/09/2026.

A tela diz isso no alto, e não por zelo: quem lesse «Next Cloud SAS ligado»
concluiria que o Registro de Imóveis inteiro está integrado, e **o índice real
pararia sem ninguém ver**.

> **O indicador real continua esperando uma coisa sua**: o par
> `client_id`/`client_secret` do ONR. Ele é pedido junto com a adesão, e é a
> mesma credencial que a Central usa.

---

## A tela

**Registro de Imóveis → Carga do Next Cloud SAS**
(`/registro-imoveis/onr/next-cloud-sas`)

Ela **só lê** — não manda nada, não grava nada, e pode ser aberta quantas vezes
você quiser. Faz três coisas:

1. **Responde se a base está completa**, com o que o ONR exige ao lado de cada
   número;
2. **Gera o XML da carga completa** do Indicador Pessoal;
3. **Confere a pasta das imagens** contra o padrão do ONR, e lista as
   matrículas que não têm imagem nenhuma.

**Ela não diz «pronto» nem «não pronto», e isso é de propósito.** Mandar a base
como está — com a declaração assinada — ou digitalizar antes é decisão sua. Um
verde ou vermelho na tela seria o sistema decidindo no seu lugar.

---

## O caminho, na ordem

> ### ⚠ A ORDEM AQUI ESTAVA ERRADA, e a pergunta do oficial corrigiu
>
> Este roteiro punha «mandar o formulário» como passo 1 e «decidir sobre o que
> falta» como passo 2. **É o contrário** — e eu só descobri porque ele
> perguntou *«qual a necessidade do formulário de adesão?»* e eu fui abrir o
> arquivo. **Eu o havia recomendado sem lê-lo.**
>
> O formulário **não é cadastro: é uma DECLARAÇÃO assinada com o e-CPF**, e
> uma das coisas que ela declara é justamente que a base está completa. A
> decisão sobre o que falta vem **antes**.

### 1. Entender o que o formulário é

`FONTES_EXTERNAS/onr_nextcloud/formulario_solicitacao_backup.pdf`, 7 páginas,
versão 2.0. Ele serve a **três** coisas, e nenhuma delas é burocracia:

**a) É a declaração de que a base está completa.** Na página 5, sob
«Assinale a opção que deseja disponibilizar», estão as duas caixas:

> «Declaro que o Indicador Pessoal Simplificado está com a base completa
> **desde o dia 1º de janeiro de 1976** (...) até a data atual.»
>
> «Declaro que esta serventia possui **todas** as matrículas digitalizadas do
> livro 2.»

E a página 6 manda **assinar digitalmente com o certificado ICP-Brasil**.

**Hoje nenhuma das duas se marca com verdade** — medido em 04/09/2026:

| a caixa diz | o que está medido |
|---|---|
| IPS com a base completa | **2.819 de 3.992** pessoas **sem CPF/CNPJ** |
| todas as matrículas digitalizadas | **74 de 1.701** **sem uma única imagem** |

**b) É o que faz o ONR criar o projeto no Google Cloud.** E para isso ele pede
uma coisa que talvez você não tenha ainda:

> «**É necessário informar uma conta do Gmail** para acesso ao Console do
> Google Cloud Platform para gerenciamento das credenciais de acesso.»

**Essa conta passa a ser a que controla os dados desta serventia** — é por ela
que você concede, altera e revoga acesso, inclusive o do próprio ONR (que fica
restrito a leitura, e só por API). Vale ser uma conta da serventia, e não
pessoal de alguém que pode sair.

**c) É onde entram os dados técnicos para instalar o IPS e o CSL2.** O suporte
do ONR liga para o técnico que você indicar — «para configurar a carga inicial
e caso ocorra algum erro de atualização».

### 2. Preencher — o que eu já medi, e o que só você tem

**Medido, e pode copiar:**

| campo do formulário | valor |
|---|---|
| Nome do Cartório | Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA |
| CNS | **000000** |
| Comarca / Estado | Cidade Exemplo / MA |
| **Total de Matrículas** | **1.701** |
| **Última Matrícula** | **4013** |
| **Espaço utilizado (Livro 2)** | **0,44 GB** |
| Diretórios a incluir no backup | `C:\ARPNET\C11\ONR\IMAGENS` |
| Qual sistema utiliza? | **Outros — Cartório Gestão** (a lista dele traz Siplam/ControlM, Siscart, Cartoon, Ocian Bit, Outros) |
| **Gmail do Cartório ou Oficial** | **`conta.google@exemplo.invalid`** — informado pelo oficial em 07/09/2026 |

> ### A conta do Google não é o e-mail de contato do cartório
>
> **Correção do oficial, no minuto seguinte**: *«esse é email do google, nao
> oficial da serventia para contato geral»*.
>
> E a correção é do meu raciocínio, e não do rótulo. Eu havia achado o mesmo
> endereço em `Empresa.Email` e `tbEmpresa.strEmail` do acervo e escrito que
> «as três fontes batem» — como se a coincidência provasse que aquele é o
> e-mail da casa. **Não prova nada disso: prova que aquelas duas colunas
> guardam esta string.** Duas colunas com o mesmo valor são uma medição; **o
> que elas significam não se deduz de elas concordarem** — e aqui quem
> desempatou não foi o dado, foi quem conhece a casa.
>
> O que ela é: a conta do **Console do Google Cloud**, e portanto **a que
> controla os dados desta serventia**. Vale ser conta da serventia, e não
> pessoal de quem pode sair. **A senha dela não entra no sistema, em lugar
> nenhum** — e não passa por mim.
>
> **E o e-mail de contato da serventia continua não existindo no sistema.**
> Medido: `settings` não tem uma única linha com `@`. É outro campo, para
> outra coisa — entre elas o **e-mail diário de ocorrências que o ONR manda** —
> e fica declarado, em vez de ser preenchido com este por parecença.

**Só você tem:**

- o **técnico de informática responsável** — nome, telefone e e-mail;
- **nome e IP do servidor**, IP da rede e IP externo;
- a **velocidade do link** de internet, e se é cabo, rádio ou fibra;
- e uma providência que não é papel: **«será necessária a liberação de rota do
  backup no firewall do cartório»**.

### 3. Decidir sobre o que falta — ANTES de assinar

São duas saídas, e as duas são legítimas:

- **completar a base** — digitalizar as 74 matrículas e preencher os
  documentos —, e então marcar as caixas com verdade;
- **declarar o que não há**, com
  `FONTES_EXTERNAS/onr_nextcloud/declaracao_base_incompleta.pdf`. Ela tem duas
  caixas — «não possui Indicador Pessoal Simplificado» e «não possui matrículas
  digitalizadas» — e **é um papel diferente, para outro endereço**:

  | | formulário de adesão | declaração de inexistência |
  |---|---|---|
  | e-mail | `integrar-onr@onr.org.br` | **`integrar@onr.org.br`** — sem o `-onr` |
  | assunto | «Opção 2 – Cartório de Registro de Imóveis de Cidade Exemplo/MA» | «Inexistência de Indicado Pessoal Simplificado – Cartório de Registro de Imóveis de …» |

  **Os dois endereços diferem por três letras**, e é o tipo de coisa que se
  erra sem perceber. Os dois pedem assinatura ICP-Brasil.

> **E a nossa situação não é «não possui»**: a serventia **tem** as duas
> bases — 1.627 matrículas com imagem e 1.173 pessoas com documento. Ela tem
> as duas **incompletas**, que é um terceiro caso, e nenhum dos dois papéis
> descreve exatamente isso. **É pergunta para o ONR**, e vale fazê-la antes de
> assinar qualquer um deles.

### 4. Olhar a conferência na tela

Abra a tela. Ela mostra três linhas com o que o ONR exige. Hoje, medido:

| | |
|---|---|
| base desde 1º/01/1976 | **alcança** — a mais antiga é de 1951 |
| toda matrícula com imagem | **74 das 1.701 não têm nenhuma** |
| Indicador Pessoal com CPF/CNPJ | **1.173 de 3.992 têm** |

O manual do ONR diz, em maiúsculas: **«Não serão aceitas base de dados ou de
imagens parciais ou incompletas.»** São duas saídas, e as duas são legítimas:

- **digitalizar as 74 antes** — a tela lista quais são, com livro e folha, e
  cada uma leva à ficha;
- **mandar a declaração de base incompleta**
  (`FONTES_EXTERNAS/onr_nextcloud/declaracao_base_incompleta.pdf`), assinada
  com o seu e-CPF, para o mesmo e-mail — e integrar o que há.

> **Sobre os 2.819 sem CPF/CNPJ, há uma coisa que a tela avisa e você precisa
> saber.** O modelo do ONR diz que o documento «deve ser maior que zero»; os
> arquivos que **esta casa já mandou** trazem **7.812 dos 10.781** com onze
> zeros. Vale a sua regra — fazer como o E-Ofício fazia —, e o sistema gera
> assim. Mas quem assina precisa saber que está mandando o que o comentário do
> modelo desaconselha. Se o ONR recusar, o caminho é preencher documento, e não
> mudar o programa.

### 5. Assinar e mandar, e só então gerar o XML do Indicador Pessoal

Na tela, o botão **«Gerar o XML da carga completa»**. Sai um arquivo chamado
`IndicadorPessoal_CARGA_COMPLETA_2026-09-04.XML`.

**É a carga COMPLETA, e não a do mês.** A outra tela — *Arquivos do ONR* —
gera o recorte de um período, para envio avulso; o Next Cloud SAS pede tudo,
«desde 1º de janeiro de 1976 até a data atual». Depois da primeira carga, **o
próprio programa IPS faz a incremental diária sozinho** — você não gera de novo.

### 6. Conferir a pasta das imagens

Não há nada para gerar aqui: **o programa CSL2 lê a pasta direto**. O que a
tela faz é conferir que ela está no formato que o ONR espera — e ela está:

| | |
|---|---|
| arquivos | **10.227** |
| no padrão do ONR | **10.227 de 10.227** |
| 200 × 200 dpi | conferido por amostra |
| compressão sem perdas (Group 4) | conferido por amostra |

**A digitalização desta casa já nasceu no formato do ONR** — a pasta se chama
`C:\ARPNET\C11\ONR\IMAGENS` justamente por isso. Não há uma imagem para
converter.

### 7. Agendar a instalação do IPS e do CSL2

O ONR instala os dois programas no servidor da serventia, e faz isso com você.
O manual traz o link da agenda.

> ### ⚠ Antes de deixar alguém mexer no servidor
>
> O ONR tem um **módulo contra golpe**, e ele existe porque alguém já tentou.
> Entre no **Ofício Eletrônico → menu «Cartórios» → «Validação Atendimento»**:
> aparece um código na sua tela. **O analista tem de dizer esse mesmo código.**
> Se não disser, não é do ONR.

### 8. Homologação primeiro; produção só depois

O ONR abre dois ambientes. Na **homologação** o dado pode ser manipulado e
apagado à vontade — é onde se erra. Na **produção** não há como desfazer.

O manual insiste: **só peça o GoLive quando a equipe estiver familiarizada com
a operação.**

---

## O que o sistema NÃO faz, e por quê

**Ele não transmite nada ao ONR por este caminho.** Quem sobe são o **IPS** e o
**CSL2**, programas deles instalados aqui. Escrever direto no Bucket e no
Firestore daria **dois caminhos gravando o mesmo fato** — e o nosso divergiria
do deles no dia em que o ONR mudasse o formato, sem ninguém perceber.

**E eu não instalo nada no servidor sem a sua palavra.** A instalação dos dois
programas é do suporte do ONR, com você na frente.

---

## Depois que estiver rodando

| o quê | quem faz | quando |
|---|---|---|
| carga incremental do Indicador Pessoal | o programa **IPS**, sozinho | todo dia |
| carga incremental das imagens | o programa **CSL2**, sozinho | todo dia |
| **e-mail com as ocorrências** | o **ONR** manda | todo dia |
| indicador real | **você**, pela *Central do ONR* | a cada matrícula |

**O e-mail diário é o que avisa quando a carga falha.** Ele vai para o endereço
que estiver no cadastro do Ofício Eletrônico — vale conferir se é um que
alguém lê.

---

## Onde estão as coisas

| | |
|---|---|
| a tela | *RI → Carga do Next Cloud SAS* |
| o manual do ONR | `FONTES_EXTERNAS/onr_ri/manual_integracao_cartorios.pdf` |
| os dez documentos que ele cita | `FONTES_EXTERNAS/onr_nextcloud/` |
| a pasta das imagens | `C:\ARPNET\C11\ONR\IMAGENS` |
| a decisão por trás de tudo isto | `O_NEXT_CLOUD_SAS_DO_ONR.md` |

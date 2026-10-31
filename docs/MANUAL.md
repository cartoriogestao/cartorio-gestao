# Manual geral do Cartório Gestão

Este manual é para quem usa o sistema no dia a dia: balcão, escreventes, quem
confere, quem administra e o oficial. Ele explica **como instalar e configurar**, dá um **panorama de todas as telas**
e mostra **o que cada parte faz e o que conferir antes de seguir**. Para quem
vai programar, veja `ARQUITETURA.md` e `AGENTES.md`. Material de apoio:

- instalação passo a passo, em versão curta: [`INSTALACAO.md`](INSTALACAO.md);
- programas, aparelhos e cadastros necessários (LibreOffice, navegador,
  selador, impressora de etiqueta, token A3, credenciais das Centrais):
  [`REQUISITOS.md`](REQUISITOS.md);
- regras de negócio com o fundamento de cada uma: [`decisoes/`](decisoes/README.md).

> **Normas estaduais.** O sistema nasceu numa serventia de um estado, e parte
> das regras vem do Código de Normas e do selador de lá. Onde isso acontece, o
> texto marca **(norma estadual — confira a do seu estado)**.
>
> **Exemplos fictícios.** «Mario Exemplo dos Santos», «Cidade Exemplo» e o
> CNS 000000 não existem.

## Sumário

1. [O que é o sistema e quem usa](#1-o-que-é-o-sistema-e-quem-usa)
2. [Instalação](#2-instalação)
3. [Configuração inicial](#3-configuração-inicial)
4. [Panorama das telas e funções](#4-panorama-das-telas-e-funções)
5. [Regras que valem para todos os atos](#5-regras-que-valem-para-todos-os-atos)
6. [Protocolo geral e caixa](#6-protocolo-geral-e-caixa)
7. [O selo eletrônico](#7-o-selo-eletrônico)
8. [Tabelionato de Notas](#8-tabelionato-de-notas)
9. [Registro de Imóveis](#9-registro-de-imóveis)
10. [Protesto de títulos](#10-protesto-de-títulos)
11. [Registro Civil das Pessoas Naturais](#11-registro-civil-das-pessoas-naturais)
12. [RCPJ e RTD](#12-rcpj-e-rtd)
13. [Livros, termos e acervo](#13-livros-termos-e-acervo)
14. [Certidões, papéis e modelos](#14-certidões-papéis-e-modelos)
15. [Assinatura digital com certificado A3](#15-assinatura-digital-com-certificado-a3)
16. [As Centrais](#16-as-centrais)
17. [Tarefas, pendências e o que falta informar](#17-tarefas-pendências-e-o-que-falta-informar)
18. [Ajuda e relato de problemas](#18-ajuda-e-relato-de-problemas)
19. [Backup e atualizações](#19-backup-e-atualizações)
20. [O sistema prepara; quem decide é você](#20-o-sistema-prepara-quem-decide-é-você)
21. [Perguntas frequentes](#21-perguntas-frequentes)
22. [O sandbox: conhecer e testar sem risco](#22-o-sandbox-conhecer-e-testar-sem-risco)
23. [O layout novo](#23-o-layout-novo)
24. [Atendimento ao cliente, rotinas e controles](#24-atendimento-ao-cliente-rotinas-e-controles)

---

## 1. O que é o sistema e quem usa

O Cartório Gestão é um sistema de gestão para serventias extrajudiciais
brasileiras. Cobre as seis atribuições — Registro de Imóveis (com o Livro 3,
Registro Auxiliar), Tabelionato de Notas, Protesto, Registro Civil das Pessoas
Naturais, Registro Civil das Pessoas Jurídicas e Registro de Títulos e
Documentos —, além do protocolo geral e caixa, do selo eletrônico, das remessas
às Centrais e da gestão interna.

- **Um computador da serventia é o servidor**: guarda banco, documentos e
  backups. Nada depende de nuvem.
- **O balcão usa o navegador.** Um atalho instalado uma vez em cada máquina
  acha o servidor sozinho na rede local.
- **Cada pessoa tem usuário e senha próprios.** Toda ação relevante fica
  registrada com o nome de quem a fez (**Auditoria**).

### Perfis de usuário

| Perfil | No sistema | Para quem | Em linhas gerais |
|---|---|---|---|
| Administrador | ADMIN | o oficial ou quem ele designar | tudo: configurações, usuários, selador, Centrais, atualizações e os atos reservados ao titular (por exemplo, encerrar matrícula) |
| Gerente | MANAGER | quem coordena o balcão | telas de gestão e acompanhamento, além do trabalho do balcão |
| Escrevente | USER | o balcão | os atos do dia a dia nas atribuições liberadas |
| Auditor | AUDITOR | quem confere ou fiscaliza | consulta telas e relatórios, **sem praticar ato** |

Uma opção ausente no menu pode decorrer do perfil ou de um módulo fechado pela
administração. O administrador nunca fica trancado do lado de fora.

---

## 2. Instalação

### 2.1 Antes de instalar: o que é preciso

A lista completa, com o motivo de cada item, está em
[`REQUISITOS.md`](REQUISITOS.md). Em resumo:

| No servidor | No balcão | Para funções específicas |
|---|---|---|
| Windows 10 ou 11 | navegador atual (Chrome, Edge ou Firefox) | aparelho selador do Tribunal (selo eletrônico) |
| Python 3.11+ (o instalador cuida disso) | impressora térmica de etiquetas | token A3 + programa do fabricante (assinatura digital) |
| LibreOffice (para os papéis saírem em PDF) | scanner (digitalização) | extensão «CG CCN Assistente» (CCN do e-Notariado) |
| Chrome ou Edge (alguns papéis em PDF) | | credenciais de cada Central |
| | | chave de um provedor de IA (opcional) |

Escolha como **servidor** um computador que fique ligado durante o
expediente, com disco folgado: o banco, os documentos digitalizados e os
backups ficam nele.

### 2.2 Instalar o servidor

1. Instale antes o **LibreOffice** no servidor, no caminho padrão.
2. Copie a pasta do sistema para o servidor, em qualquer lugar temporário.
3. Execute **`INSTALAR_SERVIDOR.cmd`** e confirme a permissão de
   Administrador. O instalador:
   - copia o programa para `C:\Program Files\CartorioGestao`;
   - cria a pasta de dados em `C:\ProgramData\CartorioGestao`;
   - prepara um Python próprio do sistema e instala os pacotes de
     `requirements.txt`. Se não houver Python 3.11+, tenta instalar o 3.12
     pelo `winget`;
   - libera no Firewall do Windows a porta **TCP 8765** (o sistema) e a
     **UDP 8766** (a descoberta automática), só para a rede local;
   - registra a tarefa **CartorioGestaoServidor**, que sobe o sistema junto
     com o Windows, mesmo sem ninguém logado.
4. Ao final, o navegador abre o sistema.

Se algo falhar, **`DIAGNOSTICAR_INSTALACAO.cmd`** mostra o motivo. O registro
fica em `C:\ProgramData\CartorioGestao\logs`.

**O que fica na pasta de dados:**

| | |
|---|---|
| `iniciar_servidor_servico.cmd` | o lançador do serviço, com o endereço do banco PostgreSQL |
| `arquivos\` | documentos anexados e digitalizações |
| `backups\` | backups automáticos e manuais |
| `updates\` | pacotes aplicados e cópias para voltar atrás |
| `secret.key` | chave das sessões de login. Não copie para outro lugar |
| `*.cred` | senhas do selador, das Centrais e dos provedores de IA, fora do banco |

Outra pasta de dados pode ser usada pela variável `CARTORIO_GESTAO_DATA`
(veja `.env.example`).

**O banco de dados é o PostgreSQL** desde a versão 3.7.0, num serviço próprio
do servidor, e não um arquivo desta pasta. O instalador ainda não o instala:
veja [`REQUISITOS.md`](REQUISITOS.md#o-banco-de-dados-postgresql) antes do
primeiro acesso.

### 2.3 Instalar os computadores do balcão

Execute **`INSTALAR_CLIENTE.cmd`** uma vez em cada computador, ou baixe o
instalador pela tela **Administrativo → Configuração → Rede / acesso**. Ele
cria o atalho **Cartório Gestão**, que acha o servidor sozinho: tenta o último
endereço que funcionou e, se não der, procura na rede. O balcão não precisa de
Python nem de IP fixo.

Se os computadores estiverem em redes separadas (VLAN, Wi-Fi de visitantes,
isolamento de clientes), quem administra a rede precisa liberar o tráfego
entre eles. No servidor, **`REPARAR_REDE.cmd`** refaz as regras do firewall,
reinicia o sistema e mostra os endereços encontrados.

> **Não exponha a porta 8765 à internet.** Para acesso de fora, use VPN
> montada por um profissional de TI.

### 2.4 Assinatura A3 e extensão do CCN

Só se a serventia for assinar digitalmente ou usar o CCN:

1. **Na máquina onde o token fica plugado**, instale o programa do fabricante
   do token (ele instala o driver) e deixe o **serviço local de assinatura**
   em execução:

   ```bat
   "%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" "C:\Program Files\CartorioGestao\a3_servico_local.py"
   ```

   Ele escuta só em `127.0.0.1:8766` e pede o PIN a cada assinatura.
2. **Para o CCN**, carregue a extensão no Chrome ou Edge:
   `chrome://extensions` → **Modo do desenvolvedor** → **Carregar sem
   compactação** → pasta `ccn_assistente\extensao` da instalação.

Detalhes, e a lista de drivers reconhecidos, em [`REQUISITOS.md`](REQUISITOS.md).

### 2.5 Desinstalar

Use **Configurações do Windows → Aplicativos instalados**. O desinstalador
pergunta se os dados devem ser apagados, e o padrão é **preservá-los**.

---
## 3. Configuração inicial

### 3.1 Primeiro acesso e usuários

1. Depois da instalação, a tela **Configuração inicial** pede nome, usuário e
   senha do primeiro administrador (**Criar administrador e iniciar**). Depois
   disso, entra-se pela tela de **Login**.
2. Em **Administrativo → Configuração → Usuários**, crie uma conta por pessoa
   (nome, usuário, perfil, senha). Em **Cargos**, escreva um cargo por linha —
   é o texto que sai embaixo da assinatura — e escolha a **Função** de cada
   pessoa. Quem sai da serventia é **desativado**, não apagado: o histórico
   continua apontando para a pessoa certa.

### 3.2 Configurar a serventia

Em **Administrativo → Configuração → Configurações**, seção **Serventia e
rede**, preencha os dados da serventia (nome da unidade, registrador e
substituto, cidade, UF e o que mais a tela pedir). **O sistema não traz dado de
serventia nenhuma**: papéis e remessas saem com o que estiver ali. Na mesma
tela:

- pastas de arquivos e de backups (vazio = padrão);
- **tempo de inatividade da sessão**, em minutos (720 = 12 horas) — sessão
  longa é comodidade com preço;
- **política de senhas**;
- **botão de imprimir**: PDF ou `.odt` (o outro formato fica ao lado);
- **Módulo de Protesto — quem pode abrir**: só o administrador (padrão), todos
  ou ninguém. Fechar não apaga título nem ato; muda só quem vê as telas;
- listas do balcão (classificações, vias de entrada, setores) e backup (seção 19).

**Salvar configurações** grava a primeira seção; cada linha de Centrais tem o
seu próprio **Guardar**.

### 3.3 Feriados e tabela de custas

- Prazos em dias úteis contam feriados. Os **nacionais** o sistema calcula. Os
  **locais** (estaduais e municipais) ainda não têm tela própria: ficam na
  configuração `ri_feriados_locais` (tabela `settings`), com uma data por linha
  no formato `AAAA-MM-DD`, e um comentário opcional depois de `#`. Peça a quem
  administra a instalação para cadastrá-los antes do primeiro prazo.
- Emolumentos e fundos são calculados pela tabela vigente **na data do ato**.
  **Administrativo → Dinheiro → Emolumentos** procura itens e calcula valores.
  Tabela, itens e fundos são **(norma estadual — confira a do seu estado)**:
  confira se a tabela carregada é a do seu Tribunal e a data de vigência.

### 3.4 O selador

Em **Administrativo → Configuração → Selador — configuração**:

1. informe o endereço do selador e, se houver, o de autenticação. Com o
   selador em produção, a tela não mostra campos de homologação; eles só
   aparecem numa instalação que ainda esteja em homologação;
2. **Ver a impressão digital**, confira o código com quem instalou o aparelho e
   só então **Conferi — pode fixar**. O sistema fixa o certificado do aparelho:
   se ele mudar, para de selar e avisa;
3. informe usuário e senha da serventia no aparelho e **Gravar** — a senha fica
   fora do banco e nunca volta à tela;
4. **Testar a conexão** antes do primeiro ato.

Selador, caminhos de selo e códigos de ato seguem o padrão do estado de origem
**(norma estadual — confira a do seu estado)**.

### 3.5 Centrais, etiqueta e rede

- **Centrais**: em **Configurações → Centrais — credenciais das APIs**, cada
  Central tem uma linha com ambiente e campos (usuário e senha, par de
  credenciais com o nome que a Central usa, ou token). As credenciais ficam
  fora do banco e não voltam à tela. Comece pela homologação quando houver. O
  que cada Central faz está na seção 16; a forma de cada credencial, em
  [`REQUISITOS.md`](REQUISITOS.md).
- **Impressora de etiqueta**: medidas e margens se ajustam em **Tabelionato de
  Notas → Ajustar etiqueta** (firma e autenticação, padrão 100 × 30 mm) e
  **RCPJ e RTD → Ajustar a etiqueta de registro** (padrão 90 × 40 mm). Imprima
  um teste, meça e ajuste aos poucos.
- **Rede**: **Administrativo → Configuração → Rede / acesso** mostra o endereço
  do servidor e oferece o instalador do balcão. **Não exponha o sistema à
  internet**; para acesso externo, VPN montada por profissional de TI.

---

## 4. Panorama das telas e funções

O menu tem quatro grupos:
- **Atalhos:** a visão geral do dia.
- **Atribuições:** as seis atribuições.
- **Operação:** livros, acervo e processos.
- **Gestão:** dinheiro, atendimento, a casa, ajuda e configuração.

Dentro de cada grupo, a ordem é a do dia: primeiro o que o balcão faz sempre,
depois consulta e acervo, e por último o que se configura uma vez. Cada módulo
tem uma cor, que aparece na faixa do alto, ao lado do título e no menu. Toda
tela tem a janela de **Ajuda** (seção 18).

As tabelas abaixo dão um panorama, tela por tela. O uso detalhado de cada
módulo vem nas seções seguintes. Uma tela pode não aparecer para você por
causa do seu perfil ou porque a administração fechou o módulo.

> **Layout novo.** Estas tabelas seguem o menu de sempre, que continua sendo o
> padrão. Quem escolheu o layout novo acha as mesmas telas pela barra de módulos,
> pela busca e pelo botão **Novo** (seção 23).

### Atalhos

| Tela | Para quê |
|---|---|
| Visão geral | a primeira tela do dia: avisos, tarefas vencidas, protocolos parados, atos sem conclusão e comunicações pendentes |
| Projetos | os projetos de desenvolvimento da casa, só para o administrador |

### Tabelionato de Notas

| Seção | Telas | Para quê |
|---|---|---|
| Painel | Painel do tabelionato | o resumo do dia nas Notas |
| O balcão | Reconhecer firma · Autenticar cópia · Pública forma · Comunicação de venda de veículo | os atos de balcão, com selo e etiqueta |
| Instrumentos | Escrituras públicas · Atas notariais · Atos de livro | lavrar, revisar e lançar no livro os atos de livro |
| Consulta | Cartões de autógrafo · Sinais públicos · Reconhecer sinal · Pendências das escrituras | fichas de firma, sinais e o que falta nas escrituras |
| Livros e remessas | Livros do tabelionato · Remessa às centrais · Cadastro no CCN · Consulta ao CCN | livros, termos, CENSEC/DOI e CCN do e-Notariado |
| Configuração e modelos | Ajustar etiqueta · Modelos dos documentos | medidas da etiqueta e os papéis das Notas |

### Registro de Imóveis

| Seção | Telas | Para quê |
|---|---|---|
| O dia | Protocolo / prenotação · Pedidos em andamento · Matrículas · Certidões · Rascunhos de ato · O que revisar antes de selar · Numeração dentro do teor | do título que entra até o ato lavrado e selado, e a certidão |
| Processos longos | Usucapião extrajudicial · Retificação de área | processos com prazos, notificações e decisão |
| Livro 3 | Registros · Minutas a revisar · O que revisar antes de selar · O que falta conferir · Certidões · Modelos | o Registro Auxiliar |
| Consulta e acervo | Indicador Real · Indicador Pessoal · CNIB (consulta, pendências, cópia local, consulta de CPF ou CNPJ na Central) · ONR (índice real e editais, certidões a emitir, acompanhamento de títulos, endereços, atendimentos do SAEC, cobranças) · Revisar transcrições em lote (IA) · Atas de ocorrência · Fichas digitalizadas · Matrículas em Word | consultas, Centrais e o acervo digitalizado |
| Modelos | Modelos de atos · Modelos de documento | os textos dos atos e dos papéis do RI |
| Remessas e obrigações | Selos e emolumentos · Exportação ONR · Indicador Real: o arquivo inteiro · Carga do Next Cloud SAS · CTP · DOI | o que se envia às Centrais, à Receita e às prefeituras |
| Configuração | Delegatários · Numeração das matrículas | quem assina e de onde parte a numeração |

### Protesto

| Seção | Telas | Para quê |
|---|---|---|
| O balcão | O roteiro das Centrais · Títulos · Certidões · Instrumentos · Devedores · Boletos | o roteiro diário, a ficha de cada título e a cobrança do devedor |
| O dia da CRA | Remessa da CRA · Imagens dos títulos · Avisos e editais · Desistências · A protestar · Retorno à CRA · Pedidos da CRA · CRA — falar pela API | os arquivos da CRA, na ordem do dia |
| O dia da CENPROT | Pendências da CENPROT · Intimação Digital · Chave do CENPROT | anuências, cancelamentos, certidões e intimação eletrônica |
| Livros e repasses | Livro de Pagamentos · Livro de Protocolo · Repasses ao apresentante · Certidão diária em relação | os livros por período, o que se deve ao apresentante e a relação das entidades |
| Do oficial | Afirmações expressas · Correções de ofício do Protesto | o que se afirmou contra uma regra, e a fila de correções |
| Modelos | Modelos dos documentos | os papéis do Protesto |

### Registro Civil das Pessoas Naturais

| Seção | Telas | Para quê |
|---|---|---|
| O balcão | Assentos · Importar pré-cadastros · Averbações · Certidões · Materializar certidão de outra serventia · Folhas de segurança · Pedidos da Central · Documentos avulsos | o dia a dia do civil |
| Nascimento | Novo registro · Digitar já lavrado · Teores · Registro tardio · Gêmeos · CPF do registrado | o registro de nascimento e as formas especiais |
| Casamento | Registro · Digitar já lavrado · Habilitação → Edital de proclamas → Enviar ao e-Proclamas → Prontas para casar · Teores | a habilitação na ordem da lei, e o assento |
| Óbito | Novo registro · Digitar já lavrado · Teores · Comunicações mensais · O que falta perguntar | o óbito e as comunicações que ele gera |
| Assento já lavrado | Retificação e suprimento · Atos sem checklist · Termos a escrever · Termos a digitalizar · Informações importadas · CPF nos assentos antigos · Matrículas · Conferência da filiação | o que se faz depois do registro |
| Comunicações e remessas | O que comunicar hoje · SIRC · FUNAI · Carga da CRC · Anotações devidas · Anotação da CRC · IBGE | as comunicações obrigatórias, cada uma com o seu prazo |
| Modelos | Modelos dos documentos | os papéis do civil |

### RCPJ e RTD

| Seção | Telas | Para quê |
|---|---|---|
| O balcão | Títulos apresentados (RTD e RCPJ) · RTD — notificações extrajudiciais · RCPJ — autenticação de livros · Etiquetas de selos externos · Central ONRTDPJ | protocolo, qualificação, notificação, livros contábeis e a fila da Central |
| Registro já lavrado | Registros lavrados (RCPJ e RTD) · Últimos atos · RCPJ — atos sem lista de presença · Certidões de inteiro teor | consulta, saneamento e certidão |
| Configuração e modelos | Ajustar a etiqueta de registro · Modelos dos documentos | etiqueta e papéis |

### Operação

| Tela | Para quê |
|---|---|
| Livros e termos | abrir e encerrar livros, termos de abertura e encerramento, inutilizar folha |
| Encerramento diário | fechar o dia dos livros de protocolo |
| Numeração dos livros | os contadores de cada livro, e os que só o oficial informa |
| O que falta informar | as pendências que só o oficial pode resolver (por exemplo, o próximo número de um livro antigo) |
| Importar de outro sistema · Importar matrícula do RI | trazer acervo de outro sistema pelo padrão JSON |
| Processos | processos internos, com prazos |
| Inspeções | o plano de ação das inspeções da Corregedoria |

### Gestão

| Seção | Telas | Para quê |
|---|---|---|
| Dinheiro | Caixa · Protocolo geral · Protocolos parados · Depósito prévio · Cobrança por boleto · NFS-e · Despesas · Carnê-leão · Recibos · Emolumentos · Selos emitidos · Selo e caixa · Selos × caixa (conferência) · Selos cancelados · Gratuidades (Portal do Selo) · Livro Diário Auxiliar | o caixa e o protocolo, que são um só trilho; o razão dos selos; boleto, nota, despesas e livro diário (seções 6.3 e 7) |
| Atendimento | Atendimento / senhas · Senhas: espera e atendimento · WhatsApp · Portal do cliente · Robôs · O que ficou pelo caminho · Envios às Centrais · Leitura dos textos (IA) · Caixas para o visto · Relatório de erros · Relatório anual de IA · Apostila de Haia · Integrações do Protesto · Rascunhos · Produtividade · Consultar fraudes · Relatórios · Painel no celular | o acompanhamento do dia e o que não terminou (seção 24) |
| A casa | Atenção para fraudes · Checklists · Correções de ofício · Obrigações recorrentes · Livros obrigatórios · Ouvidoria · Convite para avaliar · LGPD e governança · TI e infraestrutura · Auditoria · Integridade | governança e controle interno (seção 24) |
| Ajuda | Ajuda do sistema · Avisos da serventia · Problemas relatados · Base de conhecimento · Avisos ao cliente (andamento) · Automação (rotinas) | dúvidas, avisos, relato de problemas e as rotinas da casa (seção 24) |
| Modelos | Modelos dos documentos · Modelos do caixa | o catálogo geral dos papéis |
| Configuração | Configurações · Usuários · Verificação em duas etapas · Selador · Rede / acesso · Correções e atualizações · Corrigir dado do acervo · Ajuda (configurar) · Agente (configurar) · PLD / COAF | a administração da instalação (seções 3, 19 e 24) |

Algumas telas dependem de configuração ou de módulos opcionais, como os
robôs, o atendimento por WhatsApp e a ajuda com IA, e só aparecem depois de
ligadas pela administração.

---
## 5. Regras que valem para todos os atos

**Rotina diária.** Entre com o seu usuário; abra a **Visão geral**; veja as
filas da sua atribuição; **abra o caixa antes de receber**; ao terminar cada
ato, confira documento, selo, recibo e comunicação; ao fim do dia, faça o
**encerramento diário** dos livros e o **fechamento do caixa**.

**Pesquise antes de criar.** Busque pelo identificador da atribuição
(matrícula, número do assento, número do registro, título, protocolo) e
confirme o resultado antes de editar. Nunca crie registro novo para contornar
erro de um existente.

**Minuta não é ato.** A minuta permite revisar antes de ocupar lugar no livro.
Use a **prévia**: marcadores como `[CAMPO]`, `{ESCOLHA}` ou `[COMPLETAR: …]`
indicam pendência e não podem chegar ao papel assinado; a prévia de ato não
lavrado sai marcada **RASCUNHO — ATO NÃO LAVRADO**. Confira natureza, nomes,
CPF/CNPJ, livro, folha, termo, matrícula, custas e fundamento antes de lavrar.

**Rascunho guardado.** Várias telas de lavratura guardam o preenchimento para
continuar depois (**Administrativo → Atendimento → Rascunhos**). Rascunho não
toma número, não ocupa folha e não pede selo.

**Lavrado é definitivo.** Corrige-se pela ação própria (averbação,
retificação, cancelamento, estorno), com motivo; as telas registram antes,
depois, autor e motivo. **Não apague a história do ato.** Se a correção atinge
papel entregue ou comunicação enviada, veja se é preciso retificar e comunicar
de novo.

**Acervo e ato novo.** Importar é trazer o que já existia, preservando teor e
origem, sem inventar o que o documento não comprova. Registro de acervo pode
não ter selo nem responsável no sistema; isso é esperado. A ficha mostra a
origem.

---

## 6. Protocolo geral e caixa

Aqui **protocolo geral e caixa são a mesma coisa**: os serviços pedidos entram
no protocolo e, pagos, caem no caixa com os fundos separados.

### 6.1 Caixa — Administrativo → Dinheiro → Caixa

1. **Abrir o dia** com o saldo inicial em dinheiro. Sem caixa aberto, não se
   recebe.
2. **Lançar**: natureza, forma de pagamento, valor, protocolo, pagador,
   documento, descrição. Na composição de emolumentos, use os valores efetivos.
   Os campos de fundos da tela seguem a lei do estado de origem **(norma
   estadual — confira a do seu estado)**.
3. **Recibo**: nasce do lançamento e congela o teor; reabrir não cria recibo
   novo. Segundas vias em **Recibos**.
4. **Corrigir**: caixa aberto — alterar, estornar ou excluir, com motivo; caixa
   fechado — só estorno.
5. **Fechar**: informe o valor contado e justifique diferença. PIX e cartão não
   entram no dinheiro físico.
6. **Conferir**: quem fecha não confere o próprio caixa; outra pessoa
   autorizada confere depois (**Conferi**).

### 6.2 Protocolo geral

Em **Protocolo geral**, abra o atendimento com interessado, contato,
finalidade, atribuição, previsão de entrega e documento apresentado.

- **Quitar um item lança no caixa**, pelo valor calculado quando o item entrou.
- **Um recibo para o atendimento inteiro.**
- O protocolo termina como **Entregue** ou **Cancelado**, com motivo. Com item
  pago, não se cancela: o caminho é o estorno.
- **Protocolos parados** mostra o que está sem andamento.
- O protocolo geral **não substitui a prenotação** do RI (seção 9).

A ficha do protocolo reúne também:

- **Documentos para qualificação**: os papéis que o cliente entrega, em PDF, JPG
  ou PNG. O ato ligado ao protocolo os vê na tela de lavrar. Retirar pede motivo
  e não apaga.
- **Exigências em aberto** e **Nota de exigência**: abrir, imprimir e dar por
  cumprida, em qualquer atribuição.
- **Tarefas deste protocolo**: criar uma tarefa a partir dele, ou ligá-lo a uma
  que já existe.
- **Acompanhamento pelo cliente**: o código que sai no recibo e no protocolo de
  recepção (seção 24). Trocar o código invalida o de antes.
- **Conferência de documento eletrônico** (RI): o selo sai daqui, com etiqueta e
  comprovante em PDF.

No layout novo, a ficha abre nos itens, e o resto fica em abas (seção 23.4).

**Depósito prévio** registra o valor adiantado: o depósito é recebimento;
usar o saldo não é receita nova; devolver gera saída, com motivo.

### 6.3 Boleto, nota fiscal, despesas e livro diário

- **Cobrança por boleto**: a cobrança nasce do protocolo, com o que falta pagar
  sugerido, pelo banco configurado. Ver, cadastrar e lançar no caixa é de quem
  opera o caixa. Cancelar no banco, conceder abatimento e mexer no protesto
  automático é do administrador e do gerente.
- **NFS-e**: a fila do balcão, com pendências, prontos, em envio e recusadas.
- **Despesas**: cadastrar, autorizar, pagar, conferir e o relatório do mês. Todos
  cadastram, e o escrevente vê só as que cadastrou. Autorizar é só do
  administrador.
- **Livro Diário Auxiliar**: a receita e a despesa da serventia **(norma estadual
  — confira a do seu estado)**.
- **Carnê-leão**: o imposto de renda pessoal do titular e o livro-caixa dele. Só
  o administrador vê, e a tela abre no mês anterior, que é o que se apura.

---

## 7. O selo eletrônico

- **O selo sai quando o ato é praticado**, pelo caminho que o selador conhece
  para aquele ato. O carimbo impresso traz o que o selo declara (número,
  emolumentos, fundos, marcas como «isento») e o QR de consulta.
- **Pedir de novo não compra outro selo**: cada pedido leva uma referência fixa
  do ato, e a repetição devolve o selo já obtido.
- **Todo selo obtido entra no razão** antes de o ato terminar; selo obtido e
  não vinculado aparece como tal.

**Quando o selo não sai:** leia o motivo; confira item de custas, campos
obrigatórios, conexão com o selador e **Administrativo → Dinheiro → Selos
emitidos**; corrija a causa e tente **pela ficha do mesmo ato** (use **selar
depois** quando a tela oferecer). Conforme a atribuição, o ato sem selo fica
suspenso ou é lavrado e aparece na lista de atos sem selo — a tela diz qual.
**Não crie ato duplicado para pedir selo; nunca copie selo de outro ato.**

**Selo à mão**: quando a tela permite (selador fora do ar), o selo obtido por
outro canal pode ser informado; o sistema confere se é da sua serventia e
recusa selo já usado, dizendo onde está.

**Selos emitidos** pesquisa o razão por data, especialidade, usuário, tipo de
ato, situação e número. Cancelar selo exige motivo escrito.

**Selo e caixa** diz o que falta para selar aquele ato com o pagamento em ordem:
ligar o ato a um protocolo e registrar o pagamento. A tela também lista os selos
que o oficial liberou sem pagamento e que **você** obteve, e a barra vermelha do
alto leva direto a essa lista.

**Selos × caixa (conferência)** mostra a trava do selo pago, os selos liberados
sem cobertura, as gratuidades sem comprovante e os atos aguardando cobertura.
**Selos cancelados** traz os cancelados do período e o ofício de pedido ao
Tribunal. **Gratuidades (Portal do Selo)** é a fila do ressarcimento: por selo
gratuito, o comprovante e a cópia da certidão do ato.

---

## 8. Tabelionato de Notas

**Reconhecer firma** (O balcão): busque o cartão pelo nome (três letras) ou
CPF; compare a assinatura digitalizada (sem imagem, use o cartão físico); leia
avisos de bloqueio; sem cartão, **Abrir cartão novo**. Marque a pessoa, escolha
a **espécie** (semelhança e autenticidade não se trocam), descreva o documento
(veículo e conteúdo financeiro só quando for o caso) e clique em
**Reconhecer**. **Um selo por firma.** Reimprimir a etiqueta em
**Reconhecimentos feitos** não é novo ato.

**Autenticar cópia**: folhas, tipo, documento, apresentante; confira o original
e os valores; **Autenticar**. **Um selo por folha.**

**Pública forma**: o tabelião transcreve por inteiro o documento apresentado e
certifica a transcrição. Não é autenticação de cópia: o papel que sai é dele.

**Comunicação de venda de veículo**: a comunicação ao DETRAN que vem depois do
reconhecimento de firma no documento de transferência, quando exigida **(norma
estadual — confira a do seu estado)**.

**Escrituras, procurações e atas** (Instrumentos):

1. Em **Escrituras públicas**, **Atas notariais** ou **Atos de livro**, escolha
   **Lavrar** e o modelo.
2. Partes, qualificações, bens, valores e documentos; resolva as pendências.
3. Prévia: valores, matrícula do imóvel, cláusulas e fecho. Na ata, separe
   fato observado de conclusão.
4. Confira livro, termo, folha e páginas. **Cada ato começa em folha nova**;
   face que sobra é **inutilizada** (a ficha oferece o papel); livro cheio é
   encerrado e o próximo segue a numeração.
5. A **anotação antes da lavratura** é observação interna — não é a anotação à
   margem, que é ato e tem selo.
6. O selo do ato de livro sai **depois** do lançamento; se falhar, o ato fica
   lavrado e a ficha oferece **selar depois**.
7. Emita o traslado pela ficha e confira que reproduz o teor lavrado.

No layout novo, a ficha do ato é dividida em fases, e as listas têm o botão de
lavrar direto (seção 23.4).

**Consulta e livros**: **Cartões de autógrafo**; **Sinais públicos** e
**Reconhecer sinal**; **Pendências das escrituras**; **Livros do tabelionato**
(capacidade, folha atual, termos). **Remessa às centrais** reúne as obrigações
externas — **não deduza que a remessa ocorreu porque o ato foi lavrado**.
Escrituras com imóvel trazem na ficha os campos da DOI (seção 9.5).

---

## 9. Registro de Imóveis

Seções do menu: O dia; Processos que levam meses; Livro 3; Consulta e acervo;
Modelos; Remessas e obrigações; Configuração.

### 9.1 Prenotação — Protocolo / prenotação

Informe livro de destino (2 ou 3), apresentante, documento, natureza do título,
objeto e, se houver, matrícula; **Prenotar**. A data-limite nasce em dias
úteis, com feriados; marcas que alteram o prazo ficam gravadas e saem no
comprovante. Acompanhe exigências e prazo na ficha; os documentos anexados
ficam à vista de quem lavra. Ao lavrar, amarre o ato à prenotação — é o que
prova a prioridade.

**Encerrar a prenotação** é do administrador e do gerente: o motivo vem de uma
lista e define a situação, e «Outro» pede observação. Prenotação devolvida também
entra, e tudo fica na auditoria.

### 9.2 Matrículas e atos

1. Localize a matrícula (número ou CNM) e confira imagem, teor, atos, selos e
   histórico.
2. Prepare o ato em **Rascunhos de ato** ou a partir de uma minuta: registro ou
   averbação, natureza exata, titularidade, partes, imóvel, título. A ficha
   mostra **a matrícula como vai ficar**, marcada como rascunho.
3. **O que revisar antes de selar** reúne as notas de revisão (nota não altera
   o ato sozinha). **Numeração dentro do teor** confere os atos escritos dentro
   do texto das fichas antigas.
4. Lavre e confira selo e ato. Ato sem selo pode ser **selado depois** pelo
   próprio ato, inclusive em matrícula encerrada.
5. Para encerrar a matrícula (por exemplo, transporte para ficha nova), marque
   no próprio ato de encerramento que ele encerra a matrícula — assim não se
   lavra segunda averbação. Só o administrador encerra.

**Minutas** recebidas de fora ficam como «a revisar»: não tomam número, não
selam, não cobram; a revisão pode ser guardada aos poucos; descartar exige
motivo e não apaga nada.

No layout novo, a ficha da matrícula tem abas, e o formulário de lavrar tem passos
(seção 23.4).

### 9.3 Certidões e Livro 3

**Certidões**: pesquise a matrícula, escolha a espécie, confira atos e
averbações (cancelamentos e restrições não podem sumir), emissor e assinatura;
prévia, gere, reabra e compare antes de entregar. A certidão reflete o **estado
atual**. O prazo de validade impresso segue o Código de Normas **(norma
estadual — confira a do seu estado)**.

**Livro 3**: registros, minutas a revisar, o que revisar antes de selar, o que
falta conferir (ficha × imagem do livro) e certidões, em que registro e
averbações se conferem juntos. Número de ato selado não se renumera; devolver
ato à minuta é ação própria, que deixa ata.

### 9.4 Usucapião e retificação de área

O **usucapião extrajudicial** é um processo: capa, peças, checklist, andamento,
prazos, notificações, ciência dos entes, edital, análise e decisão.

1. **Autuar** (autos, modalidade, requerente, imóvel, prenotação) e juntar as
   provas. Item dispensado do checklist exige motivo.
2. **Notificações** de titulares e confrontantes: registre forma, tentativa,
   entrega e resposta. Papel gerado não é ciência.
3. **Ciência aos entes** gera três ofícios (União, Estado, Município); abra e
   imprima cada um pelo **Andamento**.
4. O prazo do **edital** conta da disponibilização na Central — confira a data.
5. A tela **Usucapião — o que o Código de Normas exige** traz as regras com o
   artigo **(norma estadual — confira a do seu estado)**.
6. A análise organiza; **a decisão é de quem tem atribuição**. O processo
   termina quando o ato sai na matrícula.

**Retificação de área** segue a mesma lógica de processo — não é edição do
texto da matrícula.

No layout novo, os autos do usucapião ficam em abas (seção 23.4).

### 9.5 Consulta, remessas e obrigações

- **Indicador Real** e **Indicador Pessoal**: índices que devem concordar com
  as fichas.
- **Fichas digitalizadas**: arquivos e vínculos das imagens; não vincule só pela
  semelhança do número. **Atas de ocorrência**: correções feitas com motivo.
- **DOI — Receita Federal**: a declaração é **da serventia**, um arquivo por
  mês com RI e escrituras. A tela confere antes de gerar e aponta o que impede
  (por exemplo, parte cuja qualificação não diz de que lado do negócio está); a
  participação de cada parte vem sugerida em partes iguais e é editável.
  Registre o recibo depois do envio.
- **CNIB**, **ONR**, **Exportação ONR**, **Carga do Next Cloud SAS**: seção 16.
- **ONR — certidões a emitir**: os pedidos que chegam pelo Ofício Eletrônico.
  Custas, enviar, finalizar e devolver são um clique sobre um pedido; buscar só
  lê. **ONR — acompanhamento de títulos**: o que espera subir, com o motivo, o que
  já subiu e o que foi anulado.
- **Exportação ONR** tem também o botão **Indicador Real (.XML)**. Ele leva as
  matrículas abertas no período que estão completas, e a tela lista as que ficam
  de fora, com o motivo. O formato ainda não foi conferido por uma resposta do
  ONR. O quadro **Digitalização nova ainda não enviada ao ONR** mostra o que a
  rotina diária ainda vai levar; nada ali envia.
- **Indicador Real: o arquivo inteiro** leva todo imóvel ativo em um arquivo só. Onde a
  ficha está em branco, vale o que o texto dela diz e, depois, a regra da serventia.
  **Nenhuma ficha muda e nada é enviado.** Use **Conferir o que sairia** e **Baixar o
  arquivo**: o `.zip` traz o XML e os relatórios do que ficou fora, de onde veio cada
  dono e cada campo preenchido. Conferir e baixar são do administrador e do gerente.
  Só o administrador decide as **fichas que não vão**, os **donos informados** e a
  **regra da serventia**, como o que vale quando a ficha não diz se é rural ou urbana.
  Instalação nova nasce sem nenhuma dessas decisões.
- **CNIB: consultar CPF ou CNPJ** pergunta à Central, com o cliente na frente, o que
  pesa sobre aquele documento agora. É diferente da tela **CNIB**, que olha a cópia
  local. Ela só diz que não há ordem quando a Central disse: se a resposta não vier
  clara ou a rede cair, a tela avisa que isso **não** quer dizer que não há ordem. A
  resposta vale para aquele documento: homônimo com outro documento não entra. Cada
  consulta fica na auditoria.
- **ONR: atendimentos do SAEC** é a lista de atendimento do portal do ONR: contato,
  WhatsApp, e-mail, LGPD, help desk, acompanhamento registral e resposta de exigência.
  **Pedido de certidão não chega por aqui:** ele está em **ONR — certidões a emitir**. O
  que espera a serventia vem primeiro. Ler é do balcão; **responder é só do
  administrador**, e vai ao ONR em nome da serventia.
- **ONR: cobranças** mostra o que o ONR tem e as tentativas feitas por este sistema. Só
  o administrador gera cobrança, pela ficha do atendimento ou por esta tela. O
  atendimento não traz o endereço do pagador, e o ONR o exige. **Abra o link e confira o
  valor antes de passar ao cliente:** o manual do ONR se contradiz sobre a forma de
  mandar o valor. O sistema não cancela cobrança: isso é no portal.
- **Revisar transcrições em lote (IA)**: a IA compara o texto de cada ficha
  transcrita com a página do livro e separa o grave do leve. Ela não corrige nada:
  a lista diz onde conferir.
  **CTP — prefeituras** e **Selos e emolumentos** também ficam em Remessas e
  obrigações.
- **Delegatários** e **Numeração das matrículas** são configuração restrita.

---

## 10. Protesto de títulos

O módulo pode estar fechado para o balcão (seção 3.2). Seções: O balcão; O dia
da CRA; O dia da CENPROT; Livros e repasses; Do oficial; Modelos.

**O roteiro das Centrais** é o checklist do dia, com o horário de cada envio e
atalho para a tela de cada passo. A coluna «hoje» conta, não julga atraso.
Passos e horários são os combinados com a Central do estado de origem **(norma
estadual — confira a do seu estado)**.

**O dia, em ordem:**

1. **Remessa da CRA**: envie o arquivo e **Conferir** — leia lotes, títulos e
   irregularidades antes de receber. Ao receber, cada título é cadastrado e
   apontado e sai a confirmação. **O mesmo arquivo não entra duas vezes.**
2. **Imagens dos títulos**: cada imagem só se prende quando o número do título
   e o documento do devedor batem.
3. **Avisos e editais**: confira destinatários e endereços; registre a entrega
   (tentativa frustrada não lavra intimação); publique o edital quando couber.
4. **Desistências**: confira de manhã, no recebimento do meio do dia e antes de
   protestar.
5. **A protestar**: a lista mostra os intimados sem movimento e conta os dias.
   **O sistema não calcula o prazo legal nem decide se venceu** — você marca e
   clica em **Lavrar o protesto dos marcados**.
6. **Instrumentos**: emita e confira assinatura e selo.
7. **Retorno à CRA**: **Gerar retorno + andamento** (saem em par); confira
   rejeições e prova de envio.

**Títulos**: a ficha acompanha apontamento, coobrigados, aviso, edital,
pagamento, desistência e cancelamento; a busca procura também pelo devedor.
**Sustação judicial**: registre juízo, processo e data do recebimento; título
sustado não se paga, protesta nem retira sem autorização judicial; revogada, o
título volta no alto da lista. **Cancelamento** exige hipótese legal e
fundamento escrito. **Certidões**: a busca roda de novo na emissão e o teor
congela; não sai negativa para quem tem protesto.

**O dia da CENPROT**: **Pendências da CENPROT** reúne anuências, pedidos de
cancelamento, pedidos de certidão, decisões judiciais e propostas de
renegociação. **Decidir e enviar são dois botões**, e a tela não lavra ato — o
cancelamento continua na ficha do título. **Chave do CENPROT** mostra, recolhida
junto da contagem, a lista dos títulos que esperam a chave.

**Na CRA:** **Pedidos da CRA** é o que veio de lá e ainda espera a casa. **CRA —
falar pela API** mostra o estado da ligação e o que dá para trazer. Em **Retorno
à CRA**, cada arquivo gerado abre os atos que levou, e o que foi desfeito depois
sai marcado.

**No balcão:** **Devedores** lista quem tem título em andamento, com os alertas
primeiro. **Boletos** mostra os títulos que podem ter boleto, os emitidos e as
pendências.

**Livros e repasses:** **Livro de Pagamentos** e **Livro de Protocolo**, por
período. **Repasses ao apresentante**, com as pendências e as guias. **Certidão
diária em relação**, com as entidades e o que falta gerar e entregar.

**Do oficial:** em **Afirmações expressas**, cada vez que a escrevente insiste em
algo que a regra diz ser erro, fica escrito por que ela seguiu, com quem, quando
e qual regra. **Correções de ofício** é a fila das correções propostas, com as
abas Propostas, Executadas, Recusadas e Falhas.

---

## 11. Registro Civil das Pessoas Naturais

Seções: O balcão; Nascimento; Casamento; Óbito; Assento já lavrado;
Comunicações e remessas; Modelos.

**Nascimento.** Pesquise antes. Preencha registrado, pais, declarante e local
com base no documento. Confira CPF e a ordem de nascimento de **gêmeos** (cada
assento leva a sua, ligados entre si). No **registro tardio**, a tela calcula se
a dispensa de testemunhas se aplica e diz por quê **(norma estadual — confira a
do seu estado)**. Primeira certidão e segunda via têm selos diferentes; siga a
tela.

**Casamento — a habilitação é um processo:**

1. **1 · Habilitação**: checklist de cada nubente; dispensa exige motivo.
2. **2 · Edital de proclamas** e **2b · Enviar ao e-Proclamas** (ou protocolo
   manual quando a Central estiver fora); anote a data efetiva.
3. Oposição: registrar, decidir e habilitar são etapas separadas.
4. **3 · Prontas para casar**: habilitação vencida (90 dias, Código Civil) é
   recusada.
5. **Registro do casamento**: confira teor, regime de bens, nomes adotados,
   selo e certidão. Se a habilitação veio de outra serventia, a tela pergunta —
   é o que define o selo do assento.

Não altere a data de publicação para liberar uma etapa bloqueada.

**Óbito.** Registre pessoa, falecimento, causa, quem atestou, sepultamento e
declarante. **O que falta perguntar** reúne as respostas que disparam
comunicações (eleitor, filhos, bens, pessoa não identificada).

**Assento já lavrado.**

- **Averbação**, **anotação** e **retificação** são atos distintos, em blocos
  próprios na ficha.
- **Retificação e suprimento**: corrigir, restaurar ou suprir, com fundamento;
  a decisão pode exigir consulta prévia à CRC **(norma estadual — confira a do
  seu estado)**.
- **CPF nos assentos antigos**: CPF por averbação, demais dados por anotação
  **(norma estadual — confira a do seu estado)**. Veja se já existe averbação
  antes de criar outra. O sistema não busca CPF em base nenhuma.
- **Matrículas**: a matrícula nacional deve aparecer completa no teor e na
  certidão. **Atos sem checklist**, **Termos a escrever**, **Informações
  importadas** e **Conferência da filiação** tratam pendências do acervo.

**Certidões e folhas de segurança.** Escolha a espécie, revise teor,
matrícula, averbações, emissor e selo; gere, reabra, confira. A certidão segue
o modelo nacional, num molde `.odt` por espécie, ajustável (seção 14). A folha
de segurança é estoque: só se gasta quando o selo sai; folha estragada se
**inutiliza** com motivo. Segunda via é nova emissão sobre o mesmo assento —
**não duplique o assento** se ela falhar.

**O caminho de uma folha**, em **Folhas de segurança**, procura a folha pelo
número impresso, com ou sem a série, e diz a situação de hoje, em que atos ela
esteve e quem a devolveu.

**Materializar certidão de outra serventia** sela a materialização da certidão
eletrônica que veio de outro cartório, com os dados da certidão recebida.

**Pedidos da Central** é a fila do que chega pela Central do Registro Civil;
pedidos de **registro** se lavram pela tela de assento, não pela fila.
**Documentos avulsos** são os papéis escritos em volta do ato; o que o modelo
não sabe preencher aparece antes de imprimir.

**Comunicações e remessas.** **O que comunicar hoje** é o painel das
obrigações, na ordem do prazo: SIRC, FUNAI, CRC, IBGE e comunicações mensais de
óbito. Prazos e destinos vêm da lei e do Código de Normas **(norma estadual —
confira a do seu estado)**. **Estar no painel não é prova de envio**: confira
arquivo, destino, competência e recibo, e registre a entrega quando a tela
pedir. Assentos do acervo não contam como atraso.

No layout novo, o novo registro tem passos, a ficha do assento tem abas, a
correção tem partes e a habilitação tem fases (seção 23.4).

---

## 12. RCPJ e RTD

1. **Escolha a atribuição antes de protocolar**: **RTD — títulos apresentados**
   ou **RCPJ — títulos apresentados**. Ela define fila e livro.
2. O título recebe protocolo e o documento fica **legível na própria tela**,
   no visualizador, e disponível para baixar.
3. Qualificação negativa: **nota devolutiva**. Positiva: lavre e confira número,
   selo e documento.
4. Papel: **etiqueta de registro**. Eletrônico: resposta pela **Central
   ONRTDPJ** (seção 16).
5. **Registros lavrados** e **Últimos atos praticados** servem à conferência.
6. **Certidões de inteiro teor** reproduzem o registro e os atos posteriores;
   registro sem teor no sistema se certifica pelo livro físico.
7. **Etiquetas de selos externos**: só para selo realmente obtido em canal
   externo, conferindo número e origem.
8. **RTD — notificações extrajudiciais**: registro, diligências, certidão
   positiva ou negativa e prazos **(norma estadual — confira a do seu estado)**.
9. **RCPJ — autenticação de livros**: pedido, termos, selo e controle dos livros
   contábeis.
10. **Lista de presença no RCPJ**: na constituição de pessoa jurídica sem fins
    econômicos, e nas averbações de eleição, posse e alteração estatutária, quem
    lavra declara a lista de presença ou a certidão de não apresentação **(norma
    estadual — confira a do seu estado)**. Ato fora dessas hipóteses segue com
    justificativa escrita. **RCPJ — atos sem lista de presença**, do administrador
    e do gerente, mostra os lavrados sem essa declaração, para sanear. O que foi
    lavrado não se reescreve.

---

## 13. Livros, termos e acervo

Menu **Livros e acervo**:

- **Livros e termos**: séries, livro aberto, folha e próximo número. Abre livro
  (o número é o seguinte da série, não se digita), emite **termos de abertura e
  encerramento** em `.odt`, registra faces inutilizadas, encerra livro. O quadro
  **O que a inspeção cobra de cada livro** traz a lista de conferência, série por
  série.
- **Encerramento diário**: fecha o dia dos livros de protocolo e mostra atrasos.
- **Numeração dos livros**: configuração restrita — **não altere contador para
  corrigir um ato isolado**.
- **O que falta informar**: seção 17.
- **Livros obrigatórios** (em A casa): o que o Código de Normas manda ter e onde
  cada livro está no sistema **(norma estadual — confira a do seu estado)**.
- **Importar de outro sistema** (arquivo JSON padronizado):
  1. escolha o que importar e envie o arquivo;
  2. **Conferir**: leia resumo, recusas, duplicidades e campos ausentes;
  3. **Importar os que passaram** traz acervo (número original, sem folha nem
     selo); **Preencher o formulário do ato novo** leva **um** registro para a
     lavratura como ato novo;
  4. confira amostras depois. Acervo importado vira livro: não há desfazer.

As cargas específicas do sistema anterior da serventia de origem, que também
aparecem no menu, só servem a quem vem daquele sistema.

---

## 14. Certidões, papéis e modelos

**Formatos.** Certidões, termos, recibos, traslados e fichas saem em `.odt`;
o PDF é o LibreOffice convertendo o mesmo arquivo, sem redesenhar. Se o PDF não
puder sair, a tela avisa em vez de entregar outro arquivo calado.

**Antes de entregar**: confira nome, número, teor, averbações, emissor e
assinatura; use a prévia e **reabra o arquivo gerado**. Se a tela disse
«sucesso» e o papel não apareceu, procure **Abrir**, **Ver** ou **Baixar** no
histórico ou andamento da ficha.

**Modelos.**

- **Administrativo → Modelos → Modelos dos documentos** é o catálogo geral;
  cada atribuição tem também o seu submódulo, com **corpo**, **encerramento** e
  **rodapé** editáveis, para a atribuição inteira ou para um ato.
- **O padrão vem do sistema; o ajuste é seu.** **Voltar ao padrão do sistema**
  desfaz o ajuste.
- A tela **confere o modelo antes de gravar** e recusa o que o papel não sabe
  montar: erro de forma, ou um nome que o padrão daquele papel não usa. Corpo vazio
  não se grava.
- **A conferência olha a forma.** Um campo com o nome errado dentro de um grupo que
  existe, como `serventia.cidde`, pode sair em branco no papel. Por isso a prévia vale
  a pena.
- Os moldes `.odt` das certidões do Registro Civil se baixam, ajustam no
  LibreOffice e reenviam (**Enviar o papel ajustado**).
- Antes de alterar, faça a prévia com um exemplo. **Modelos do caixa** cobre
  recibo, orçamento e recepção.

---

## 15. Assinatura digital com certificado A3

A assinatura do delegatário usa certificado ICP-Brasil em **token ou cartão
A3**.

- **O servidor nunca carrega o token** — o driver dentro do servidor pode
  derrubar o sistema. A assinatura acontece na máquina onde o token está, por
  um serviço local que só atende a própria máquina e pede o PIN na hora.
- **O sistema não guarda chave nem PIN.**
- **O sistema confere o `.p7s` assinado**: quem assinou e se o documento é
  exatamente o emitido. **Não afirma** validade jurídica, que depende da cadeia
  ICP-Brasil e da lista de revogação.

Instalação do serviço local: [`REQUISITOS.md`](REQUISITOS.md), seção 4. As
funções que dependem de assinatura (por exemplo, a carga da CRC) só funcionam
com ele configurado.

---

## 16. As Centrais

**Princípios para todas:**

- **Conferir e enviar são dois passos**: a tela mostra o que vai antes de
  mandar.
- **Enviado não é aceito**: a Central pode aceitar parte e recusar parte na
  mesma resposta — leia o retorno item a item.
- **Homologação e produção são credenciais e registros diferentes**; a tela
  avisa quando é teste.
- **Credenciais fora do banco**, num arquivo por Central.
- **A Central não decide por você**: o que chega para decisão espera o seu okay.

| Central | Atribuição | Onde no menu | O que o sistema faz |
|---|---|---|---|
| CRA | Protesto | O dia da CRA | recebe remessas e desistências; gera confirmação, retorno e andamento |
| CENPROT | Protesto | Pendências da CENPROT; Chave do CENPROT | baixa e responde pendências; grava a chave nacional do título; envia o arquivo de emolumentos |
| Intimação Digital | Protesto | Intimação Digital | acompanha a intimação eletrônica; a intimação no livro continua na ficha do título |
| ONR | RI | ONR — índice real e editais; endereços a conferir; Exportação ONR; Indicador Real: o arquivo inteiro; ONR — atendimentos do SAEC; ONR — cobranças | envia indicador real e edital do usucapião; propõe endereços lidos do teor para você conferir; gera o arquivo inteiro do indicador; lê e responde atendimentos; gera cobrança, com clique do administrador |
| Next Cloud SAS (ONR) | RI | Carga do Next Cloud SAS | prepara e confere a carga do indicador pessoal e das imagens; quem transmite são os programas do ONR |
| CNIB | RI | CNIB — indisponibilidade; o que espera seu okay; CNIB — consultar CPF ou CNPJ | mantém a cópia local, avisa quando nome ou documento bate e **prepara** a averbação, que espera o okay. Veja a data da última atualização antes de concluir que não há restrição |
| Receita (DOI) | RI e Notas | DOI — Receita Federal | gera o arquivo mensal da serventia e guarda o recibo |
| e-Proclamas | Registro Civil | 2b · Enviar ao e-Proclamas | publica o edital de proclamas e guarda o número do lote |
| Certidão Eletrônica | Registro Civil | Pedidos da Central | traz a fila de pedidos e devolve a certidão |
| CRC Nacional | Registro Civil | Carga da CRC; Anotação da CRC; Anotações devidas | prepara a carga e as comunicações para anotação (assinatura A3) |
| SIRC | Registro Civil | Remessa do SIRC | monta a remessa, inclusive a declaração de mês sem movimento |
| IBGE | Registro Civil | Remessa do IBGE | gera o mapa trimestral e registra a entrega |
| FUNAI | Registro Civil | Comunicação à FUNAI | prepara o ofício de nascimento de indígena |
| ONRTDPJ | RCPJ e RTD | Central ONRTDPJ — a fila de lá | traz títulos eletrônicos e comunica nota devolutiva e registro decididos aqui |
| Centrais do tabelionato | Notas | Remessa às centrais | reúne as remessas obrigatórias das Notas |

Integrações que dependem de extensão de navegador ou de assinatura local (como
o CCN do e-Notariado) só funcionam com a configuração de
[`REQUISITOS.md`](REQUISITOS.md). Armadilhas de cada contrato:
[`decisoes/`](decisoes/README.md).

---

## 17. Tarefas, pendências e o que falta informar

**Processos e malote.** **Processos** é a lista de tarefas e expedientes:
entradas do malote, responsável e substituto, prazo, resposta e arquivamento
(em instalações anteriores, as telas **Expedientes / Malote** e **Tarefas e
pendências** fazem o mesmo). **Concluir a tarefa não encerra o expediente**: ele
tem etapa própria, e a tela mostra os que estão prontos para encerrar.
**Inspeções** guarda achados, plano de ação, responsáveis e prova de
saneamento.

**O que ficou pelo caminho** (Administrativo → Atendimento) mostra os atos
iniciados e não concluídos — escritura em lavratura, prenotação sem ato,
processos parados, decisões não enviadas —, medidos na hora. Ato concluído sai
sozinho. Você liga ou desliga cada fonte e ajusta quantos dias contam como
parado.

**O que falta informar** (Livros e acervo) lista o que **só o oficial pode
dizer** — por exemplo, o próximo número de um livro que a carga não trouxe. Cada
item diz o que é, por que só o oficial sabe e o que acontece sem resposta, e um
aviso aparece em todas as telas enquanto houver pendência. Responda ou dispense
com motivo escrito.

**A casa** (Administrativo):

- **Atenção para fraudes**: nomes e documentos comunicados, com o papel de cada
  um (vítima, envolvido, nome em documento fraudado) e a origem. O alerta
  aparece nas fichas por onde a pessoa entra. **Alerta não é trava** — homônimo
  é comum, e a vítima está na lista para ser protegida. Registre a conferência
  em **Consultar fraudes**: é ela que responde «o sistema avisou?».
- **Checklists**, **Obrigações recorrentes**, **LGPD e governança**, **TI e
  infraestrutura**: tarefas periódicas e inventários com responsável e revisão.
- **Auditoria**: quem fez cada operação. **Integridade**: inconsistências e
  anexos.

---

## 18. Ajuda e relato de problemas

**A janela de ajuda** existe em toda tela e sabe de onde a pergunta saiu.
Escreva o que tentou, o resultado e a mensagem de erro.

- Ela pode consultar um **provedor de IA escolhido pela serventia**. Por padrão,
  **CPF, CNPJ e outros dados pessoais são mascarados**; **Ver o que sairia**
  mostra exatamente o que será enviado.
- Ela **lê** a instalação e a documentação e **não pratica ato**. A resposta é
  orientação: confira na ficha e na norma, sobretudo em selo, prazo e dado de
  registro.
- Quem pode consultar, o provedor e a chave são definidos pelo administrador em
  **Ajuda — configurar**, com teto diário de uso. Sem chave, o sistema funciona
  normalmente. A **Base de conhecimento da ajuda** guarda verbetes da casa.

**Problemas do sistema** (Administrativo → Ajuda):

- Tela que dá erro **vira uma linha sozinha**; o mesmo erro repetido vira
  contador.
- Ao relatar, informe módulo, tela, número do registro ou protocolo, horário e
  mensagem literal — sem senha, chave ou documento sigiloso desnecessário.
- **Gerar o relatório para conserto** produz um relatório sempre mascarado.
- O desenvolvimento anota o que fez e a prova; **Resolvido** é marcação de quem
  usa e conferiu no ato real, e exige dizer o que foi feito.

**Agente do sistema** (opcional, só do administrador): apura problemas lendo a
instalação; **não pratica ato**, não executa programas e mascara dados. Suas
poucas ações de escrita nascem desligadas, e cada mudança se desfaz com um
clique.

**Agente de minutas** (RI e Notas, desde a 3.7.4): o quadro **«Agente de
minutas (IA)»** aparece na ficha da matrícula e no ato em lavratura das Notas.

1. Marque os documentos que fundamentam o ato (os da prenotação e do protocolo
   geral vêm marcados) ou junte outros na hora — eles ficam arquivados com o ato.
2. Escreva, se quiser, instruções iniciais («compra e venda de 50%»).
3. Clique em **Preparar a minuta com o agente** e aguarde alguns minutos.
4. Confira a versão inteira: o texto, as partes, o que ele não conseguiu
   afirmar e de que documento e página saiu cada dado. Para mudar algo, use
   **Instruções de revisão**.

O que falta ou está ilegível sai como `[COMPLETAR: …]`. A minuta vai para a fila
«Minutas a revisar e lavrar» (RI) ou para o teor do ato (Notas); **lavrar,
selar e cobrar continuam sendo da pessoa**, pela tela de sempre. Os documentos
sobem inteiros ao provedor de IA configurado, e há teto diário de pedidos.

**Ato feito por robô fica com o autor pendente** (desde a 3.7.3). Em sessão de
conta marcada como robô — ou sem ninguém logado —, o campo de quem praticou o
ato sai **«PENDENTE — assina quem selar»**, e o robô não sela. Quando uma pessoa
abre o ato e clica em **Selar**, o nome dela entra no lugar da marca.

---

## 19. Backup e atualizações

**Backup.**

- Em **Configurações**: pasta de backup, backup automático diário e retenção;
  **Criar e baixar backup completo** faz um na hora.
- O backup leva banco e arquivos. **Não copie o arquivo do banco com o sistema
  aberto** como forma de backup.
- Mantenha **uma segunda cópia em outro disco** ou fora da serventia.
- Credenciais (`*.cred`), `secret.key` e `cofre.key` **não vão no backup, de
  propósito**: guarde-os à parte, em local seguro, para reinstalar o servidor.
- Em **Proteção do backup** dá para ligar a **cifra do pacote** (desligada de
  fábrica) e tirar o acervo do E-Ofício do completo. Como restaurar um pacote,
  cifrado ou não: `docs/BACKUP.md`.

**Atualizações.** As versões chegam como **pacotes `.cgu` assinados** por quem
mantém o sistema, com o **SHA-256** enviado por **canal separado**. **Só o
administrador aplica**, em **Administrativo → Configuração → Correções e
atualizações**:

1. selecione o `.cgu`, cole o SHA-256 e **Validar e preparar — sem aplicar**;
2. leia a inspeção (versões de origem e destino, arquivos, alertas, plano de
   retorno);
3. repita o SHA-256, digite a confirmação, informe sua senha de administrador,
   marque que revisou e **Criar backup, aprovar e aplicar**;
4. o sistema confere o pacote e cada arquivo, faz backup, guarda a versão
   anterior, aplica e reinicia — **se o servidor novo não responder, volta
   sozinho à anterior**;
5. confira no rodapé (ou na página de saúde) a versão em execução; se não
   mudou, leia o resultado antes de repetir.

A atualização não apaga dado: o banco só recebe acréscimos.

---

## 20. O sistema prepara; quem decide é você

O Cartório Gestão organiza, calcula, confere e avisa. **A qualificação e a
decisão jurídica pertencem a quem tem atribuição.** O sistema:

- **não qualifica título nem decide procedência** (no usucapião, a análise
  organiza; a decisão é do oficial);
- **não julga impedimento** na habilitação de casamento;
- **não decide o vencimento do prazo do protesto** — conta os dias e mostra;
- **não lavra averbação de indisponibilidade sozinho** — prepara e espera;
- **não trava ato pela lista de fraudes** — avisa e registra que você viu;
- **não busca CPF em bases externas** para averbar;
- **não envia a Central sem conferência**, nem dá por aceito o que só foi
  enviado;
- **não afirma a validade jurídica de uma assinatura digital**;
- **não cobra pela média**: a receita sugerida mostra o que costuma ser cobrado,
  e você marca o que cabe no caso;
- **não inventa número, data nem teor** — pergunta em «O que falta informar» ou
  deixa em branco, porque campo vazio não afirma nada;
- **não deixa a IA decidir** — ajuda e agentes aconselham e redigem minuta,
  nunca lavram;
- **não põe no ato o nome de quem não o praticou** — robô não assina, e ninguém
  assina por ele.

Práticas que evitam a maior parte dos problemas: confira o original antes de
lavrar e o papel antes de entregar; corrija pelo caminho próprio, com motivo;
nunca reaproveite selo nem duplique registro para «destravar» algo; confira
antes de receber arquivo de Central; mantenha dados da serventia, feriados e
tabela de custas em dia; faça e confira o backup.

---

## 21. Perguntas frequentes

**O selo não saiu. Tento de novo?** Leia o motivo, confira custas, campos,
conexão e **Selos emitidos**. Repetir **pelo mesmo ato** não duplica selo;
criar outro ato, sim.

**A segunda via não sai.** Confirme que o registro existe uma vez só, que teor
e matrícula estão completos e que a espécie é a certa. Em registro importado,
relate o problema com o número. Não duplique o registro.

**O documento foi gerado mas não abre.** Procure **Abrir**, **Ver** ou
**Baixar** no histórico ou andamento da ficha (no usucapião, os ofícios aos
entes ficam nas linhas de ciência). Sem link, relate tela, processo e horário.

**A imagem da matrícula não aparece.** Veja **Fichas digitalizadas**: arquivo no
disco sem vínculo não aparece. Não vincule só pela semelhança do número.

**Há registro duplicado ou averbação errada.** Compare número, origem, teor,
datas e histórico; preserve o correto; cancele ou corrija com motivo; confira
selos e certidões já emitidos.

**Uma opção do menu sumiu.** Pode ser o seu perfil ou um módulo fechado pelo
administrador (como o Protesto).

**A Central diz que recebeu, mas continua pendente.** Recebido não é aceito:
confira o retorno item a item.

**O PDF não sai.** Confira se o LibreOffice está instalado no servidor
([`REQUISITOS.md`](REQUISITOS.md)). O `.odt` continua disponível ao lado.

**Posso acessar de casa?** Só por VPN montada por profissional de TI. Nunca
exponha o sistema à internet.

**O que é «Minuta», «Prenotação», «Teor»?** Minuta é o texto ainda não lavrado;
prenotação é o lançamento do título no protocolo do RI, que garante a
prioridade; teor é o texto do ato ou registro; razão dos selos é o histórico de
selos obtidos, vinculados e cancelados.

---

## 22. O sandbox: conhecer e testar sem risco

O **sandbox** é uma instalação de demonstração do sistema, **só nesta
máquina**, com uma serventia fictícia e dados de mentira. Serve para duas
coisas:

- **conhecer o sistema** antes de instalá-lo numa serventia — abrir as telas,
  praticar atos, emitir certidões, errar à vontade;
- **testar uma alteração no código** antes de levá-la a uma instalação real.

Nada do que você faz no sandbox chega a uma serventia, a uma Central ou ao
Tribunal. Ele não instala nada no Windows: não cria tarefa agendada, não mexe
no Firewall e não abre porta para a rede.

### 22.1 Como ligar

1. Tenha o **Python 3.11 ou mais novo** e os pacotes do sistema. Na pasta do
   programa, uma vez só:

   ```bat
   python -m pip install -r requirements.txt
   ```

   Se preferir um ambiente separado, crie um `.venv` na própria pasta do
   programa — o sandbox o usa sozinho. Para indicar outro Python, defina a
   variável `CG_PYTHON` com o caminho do `python.exe`.
2. Dê dois cliques em **`INICIAR_SANDBOX.cmd`**, na pasta do programa.
3. Na primeira vez ele monta o banco e a carga de demonstração (demora um
   pouco mais); depois o navegador abre em **http://127.0.0.1:8899**.
4. Para encerrar, feche a janela preta ou aperte **Ctrl+C** nela.

Se faltar algum pacote, a janela diz qual e mostra o comando para instalar.
Se a porta 8899 estiver ocupada, use outra: `INICIAR_SANDBOX.cmd --porta 8900`.
As outras opções são `--sem-navegador`, `--sem-carga` (não roda a carga de
demonstração) e `--dados PASTA` (outra pasta de dados, sempre de sandbox).

### 22.2 Os usuários de demonstração

As senhas são **fracas e óbvias de propósito**: o sandbox é fechado, só nesta
máquina, e existe para ser usado sem cerimônia. **Nunca** use estas senhas
numa instalação real.

| Usuário | Senha | Perfil | Nome fictício |
|---|---|---|---|
| `admin` | `admin123` | Administrador | Mario Exemplo dos Santos |
| `escrevente` | `escrevente123` | Usuário (balcão) | Beatriz Exemplo de Souza |
| `auditor` | `auditor123` | Auditor (só consulta) | Carla Exemplo Lima |

A **carga de demonstração** (`tools/carga_de_demonstracao.py`) preenche a
serventia fictícia — «Ofício Único de Cidade Exemplo/MA», CNS 000000 —, abre
um livro em cada série, recebe uma caixa de folhas de segurança de teste e
deixa alguns atos de exemplo: um nascimento e um óbito com certidão no
Registro Civil, uma procuração pública nas Notas, uma certidão negativa no
Protesto e uma matrícula no Registro de Imóveis. Ela roda toda vez que o
sandbox liga e **não duplica nada**: o que já existe fica como está, inclusive
o que você mudou depois.

### 22.3 O que fica isolado

| | No sandbox | Numa instalação real |
|---|---|---|
| Pasta de dados | `sandbox_dados` ao lado do programa | `C:\ProgramData\CartorioGestao` |
| Credenciais, `secret.key`, perfil do LibreOffice | `sandbox_dados\programdata` (vazia) | `C:\ProgramData\CartorioGestao` |
| Endereço | `http://127.0.0.1:8899`, só nesta máquina | porta 8765, para a rede local |
| Descoberta automática (UDP 8766) | desligada | ligada |
| Centrais (CRC, SIRC, CRA, CENPROT, ONR…) | desviadas para simulador ou recusadas | as de verdade |
| Internet e rede local | **travadas**: nenhuma conexão sai da máquina | livres |
| Selador | de mentira, com TLS de verdade numa porta local | o aparelho do Tribunal |
| Atualização do sistema (`.cgu`) | recusada | aplicada |
| Cookie da sessão | `cg_sandbox_sessao` | `session` |

Quatro coisas merecem uma frase:

- **O sandbox recusa subir sobre dados de verdade.** Se a pasta escolhida for
  (ou contiver, ou estiver dentro de) a pasta de uma instalação real, se tiver
  um `install.json`, ou se já guardar um banco que não foi o kit que criou, ele
  para com a mensagem e não abre nada. A variável `CARTORIO_GESTAO_DATA`
  herdada do Windows é **ignorada** — o sandbox usa só a pasta dele.
- **Os selos não existem no Tribunal.** Os dos atos que você praticar saem do
  selador de mentira, com a palavra `TESTE` no número; os dos atos de exemplo
  da carga são números de demonstração gravados à mão.
- **O cookie tem nome próprio** para o sandbox não derrubar a sua sessão numa
  instalação real aberta noutra aba do mesmo navegador.
- **Uma faixa no rodapé** de toda tela lembra que aquilo é o sandbox.

O que o sandbox **não** tem: a **tabela de emolumentos** (numa instalação real
ela é importada do E-Ofício ou do Tribunal, e preço inventado num sistema de
cartório seria pior que preço nenhum) e credenciais de Central. A matrícula de
exemplo nasce como ficha de **acervo**, porque a numeração própria do sistema
começa na 4.015.

### 22.4 Testar uma alteração no código antes de levá-la a uma instalação real

1. Faça a alteração na sua cópia do programa (a que veio do GitHub — **nunca**
   na pasta instalada; o sandbox se recusa a rodar de dentro dela).
2. Rode os testes do que você mexeu:

   ```bat
   python -m pytest tests\test_do_que_voce_mexeu.py -q
   ```

3. Ligue o sandbox (`INICIAR_SANDBOX.cmd`) e percorra a tela alterada como o
   balcão percorreria: entre com o perfil certo, pratique o ato, emita o papel.
   Depois de cada mudança no código, feche a janela e ligue de novo — o banco
   do sandbox continua, e a carga não duplica.
4. Para conferir sem abrir o navegador (útil depois de mexer em muita coisa):

   ```bat
   python tools\iniciar_sandbox.py --conferir --porta 8901
   ```

   Ele sobe o sistema, abre `/saude` e `/login`, diz quantas conexões para
   fora foram tentadas (tem de ser zero) e sai.
5. Só então empacote a atualização e leve à instalação real, pelo caminho do
   capítulo 19 — com backup antes.

### 22.5 Como apagar o sandbox

Tudo o que o sandbox grava fica na pasta `sandbox_dados`, ao lado do programa.
Para recomeçar do zero, feche o sandbox e:

- apague a pasta `sandbox_dados`; **ou**
- rode `INICIAR_SANDBOX.cmd --apagar`, que confere que a pasta é mesmo de
  sandbox (tem o arquivo `SANDBOX_DEMONSTRACAO.txt`) e pede que você digite
  `APAGAR` para confirmar.

Na próxima vez que você ligar, ele nasce de novo, com a carga de demonstração.
Se a pasta do programa não aceitar escrita, o sandbox usa
`%LOCALAPPDATA%\CartorioGestaoSandbox` — a janela mostra a pasta em uso, na
linha «dados».

---

## 23. O layout novo

O layout novo é outra moldura para as mesmas telas: menos rolagem, e só o que
importa naquele momento do ato. **Nenhuma rota, formulário ou regra muda**: o que
o sistema recusava, continua recusando. Trocar de layout não apaga nem altera
nada, e dá para voltar a qualquer hora.

### 23.1 Como ligar e como voltar

- **O layout novo é o padrão.** Quem nunca escolheu abre nele, com um aviso em todas as
  telas: **Ficar neste** ou **Voltar ao antigo**. Qualquer um dos dois grava a escolha, e o
  aviso some.
- **Cada pessoa pode trocar quando quiser.** Para voltar, clique no seu nome, no pé da
  barra de módulos, e use **Voltar ao layout antigo**. No layout antigo, o botão **Novo
  layout** fica no rodapé do menu.
- **O administrador pode devolver a casa ao antigo**, no mesmo lugar: **Devolver o layout
  antigo como padrão da casa**, que se desfaz com **Usar este layout como padrão da
  casa**. A escolha que cada pessoa já fez continua valendo para ela.
- **O timbre na tela** fica só onde se confere antes de imprimir: caixa, protocolo geral,
  prenotação e certidão de notificação. O layout antigo e o papel impresso não mudam.
- **Em monitor largo** (a partir de 1600 px), os campos passam a três colunas e alguns
  quadros ficam lado a lado. Em tela menor, nada muda.

### 23.2 A moldura

| Onde | O que é |
|---|---|
| Barra de módulos, à esquerda | Início, Notas, Registro de Imóveis, Registro Civil, Protesto, RCPJ e RTD, Caixa e Protocolo, Atendimento, Processos e Malote, Livros e Acervo, Finanças e Selos e Gestão. O que era «Administrativo» se dividiu entre Caixa e Protocolo, Atendimento, Finanças e Selos e Gestão |
| Coluna ao lado | as seções do módulo aberto |
| Faixa do alto | onde você está e as subabas da seção |
| **Buscar ou fazer** | a busca da seção 23.3 |
| Atendimento | o protocolo que você está atendendo |
| **Novo** | abrir ou lavrar qualquer coisa, sem navegar (seção 23.3) |
| Sino | os avisos da casa, e o formulário do recolhimento do mês |
| Coluna de apoio, à direita | WhatsApp, Produtividade, Ajuda e Agente, em toda tela, abrindo ao lado do conteúdo |

**Continuam à vista, fora do sino:** selo sem trava, comprovante da gratuidade,
ficha sem digitalização, selo cancelado e o aviso do caixa. O recolhimento do mês
vira uma faixa fina, sem botão de fechar.

Cada pessoa só vê o que o seu perfil alcança, como no menu de sempre.

### 23.3 Buscar e abrir pelo teclado

**Buscar ou fazer** (Ctrl+K) tem três grupos:

- **Fazer:** as mesmas ações do botão Novo.
- **Ir para:** as telas. Acha pelo nome novo, pelo nome antigo e sem acento.
- **Procurar em:** Matrículas, Atos de Notas, Cartões de autógrafo, Assentos do
  Registro Civil, Títulos de protesto e Protocolo geral.

**Novo** abre com a tecla **N**, fora de um campo de texto. A letra marca, e
**Enter** confirma: **N, P, Enter** abre a procuração pública.

| Letra | Abre | | Letra | Abre |
|---|---|---|---|---|
| F | Reconhecer firma | | T | Prenotar título |
| A | Autenticar cópia | | C | Certidão de imóvel |
| P | Procuração pública | | N | Nascimento |
| E | Escritura pública | | G | Protocolo geral |

Outras teclas: **F1** abre a Ajuda, **Alt+P** a Produtividade, **Alt+W** o WhatsApp
e **Esc** fecha o que estiver aberto.

### 23.4 As fichas divididas

Uma ficha longa aparece em partes, de uma destas três formas:

- **Fases**, quando o ato tem ordem: a régua numera, marca o que está feito e o que
  falta. Fase que depende de outra diz o que vem antes e leva até lá.
- **Abas**, quando é um registro vivo, sem ordem própria.
- **Passos ou partes**, quando é um formulário longo. **É um formulário só:** o que
  está escondido vai junto quando se grava.

Em todas:

- **O número na aba** é a contagem, e o número em vermelho é o que está pendente.
- **O endereço diz a parte aberta**, e por isso voltar, recarregar e colar o link
  funcionam. **Depois de gravar**, a ficha volta à parte em que você estava.
- **Campo obrigatório em branco numa parte escondida:** ela abre sozinha, com o
  cursor no campo.
- **A trava da tela só orienta.** Quem recusa continua sendo o sistema, com as
  mesmas verificações de sempre.
- **«O que espera ação»** vem no alto, com um botão que leva direto ao lugar. Ele
  só aparece quando há o que fazer, e o acervo não entra.

| Tela | Forma | Partes | Onde abre |
|---|---|---|---|
| Ato de Notas | Fases | Preparar · Partes · Evidências (só nas atas) · Teor · DOI (só nas escrituras) · Lançar · Entrega. De apoio: Documentos e Financeiro | na primeira fase pendente; ato lançado abre na Entrega |
| Matrícula | Abas | Resumo · Atos · Teor e imagem · Partes · Protocolos (quando há) · Certidões · Revisar · Novo ato | no Resumo |
| Novo ato da matrícula | Passos | Protocolo · Ato e teor · Selo · Partes · Lavrar | no Protocolo; minuta ou encerramento abre em Ato e teor |
| Prenotação | Fases | Título · Emolumentos · Qualificação. De apoio: Documentos, e Notas, ONR e Histórico quando há | no que espera ação, com o prazo no título da página |
| Usucapião | Abas | Processo · Conferência · Peças · Andamento · Relatório · Decisão | em Processo, que começa por «O que fazer agora» |
| Novo registro de nascimento ou natimorto | Passos | Nascimento (ou Natimorto) · Registrado · Filiação · Declarante · Termo e selo | no primeiro passo |
| Novo registro de óbito | Passos | Óbito · Falecido · Filiação · Perguntas · Declarante · Termo e selo | no primeiro passo |
| Novo registro de casamento | Passos | Celebração · Primeiro cônjuge · Segundo cônjuge · Testemunhas · Termo e selo | no primeiro passo |
| Correção do assento | Partes, sem número | O assento · Campos do termo · Teor · as pessoas, conforme a espécie. O motivo e o botão de salvar ficam sempre à vista | em O assento |
| Ficha do assento | Abas | Assento · Filiação e dados · Averbações · Anotações · Retificações · Certidões · Termo do livro · Documentos | em Assento |
| Habilitação de casamento | Fases | Habilitação · Edital · Prontas para casar · Registro. De apoio: Andamento | no que espera ação |
| Protocolo geral | Abas | Itens e quitação · Dados e encerramento · Documentos · Exigências · Tarefas · Vínculos (só no RI) · Acompanhamento · Movimento (com lançamento) | nos itens |
| Título de Protesto | Fases | Apontamento · Intimação · Desfecho. De apoio: Vida do título, Emolumentos, Imagem e, para o administrador, Averbação | no que espera ação; título encerrado abre na Vida do título |
| Título do RCPJ e do RTD | Fases | Apresentação · Qualificação · Registro. De apoio: Central e, para o oficial, Encerrar, enquanto o título não saiu | no que espera ação: apresentado ou com exigência, na Qualificação; qualificado ou registrado, no Registro (para o balcão, o qualificado abre na Qualificação); devolvido ou cancelado, na Apresentação |
| Registro do Livro 3 | Abas | Resumo · Atos (quando há) · Teor e imagem · Partes · Minutas (quando há) · Revisar · Certidões · Corrigir (para o oficial) · Lançar (com o registro ativo) | no Resumo, que começa por «O que espera ação» |
| Prenotar, no Protocolo | Passos | Apresentante e destino · O título e o selo | no primeiro passo |
| Título novo de Protesto | Passos | O título · Devedor · Apresentante e cedente. O segundo devedor vem recolhido | no primeiro passo |
| Abrir matrícula | Passos | O imóvel · Descrição · Proprietário · Abertura e teor. Ficha de acervo não tem Proprietário | no primeiro passo |
| Novo registro do Livro 3 | Passos | O título · Teor · Partes · Selo e cobrança | no primeiro passo |
| Corrigir a matrícula | Partes, sem número | Identificação · Imóvel · Rurais e fiscais · Observação. O motivo fica sempre à vista | em Identificação |
| Abrir habilitação de casamento | Passos | O casamento · Os nubentes | no primeiro passo |
| Nova retificação de área, no RI | Passos | O processo · Requerente e profissional · Área e georreferenciamento | no primeiro passo |
| Nova retificação, no Registro Civil | Passos | Qual dos três · Como o pedido chegou · Quem pede, e o quê | no primeiro passo |

**Listas e Painel de Notas.** Procurações, fins previdenciários, substabelecimentos,
revogações, renúncias e testamentos têm **Lavrar** no alto, que abre o ato direto, e
as vistas **Em lavratura**, **Lavrados** e **Todos**, com a contagem de cada uma.
Cada linha em lavratura tem **Continuar**. Escrituras e atas abrem na lista, e os
modelos e a conferência ficam na subaba **Modelos e conferência**. O Painel tem
**Lavrar agora** e **O que espera você**.

**Nas abas, o que não tem lista não aparece.** Na ficha do assento, por exemplo,
Anotações só existe quando há anotação; lançar não depende dela, porque **Lançar
no assento** está na aba Assento. No protocolo, Documentos, Exigências e Tarefas
ficam mesmo vazias, porque é nelas que se cria o primeiro.

**No título de Protesto, o Desfecho** traz um quadro por ato que cabe naquela situação.
Só um vem aberto: o protesto, quando cabe. Os outros abrem com um clique. Os avisos do
alto, como selo que falta, pedido da CRA e sustação, saem em todas as abas.

**Título novo, Abrir matrícula, Livro 3 e Corrigir a matrícula:** o botão de gravar fica numa barra
presa ao pé da tela. Antes do último passo, quem fica azul é **Avançar**. Se você gravar antes, um campo
recusado abre o passo dele, com o cursor nele. Se o proprietário, o apresentante ou o item da tabela
estiverem vazios, a barra avisa, mas não impede. Os botões de rascunho ficam na linha do Voltar.

**Prenotar, Abrir habilitação e as duas retificações:** o botão de gravar fica no último passo, e
**Salvar rascunho** e **Não termina hoje** ficam sempre à vista.

**No título do RCPJ e do RTD**, o documento fica na Qualificação, ao lado da decisão. O registro
é ato do oficial: para o balcão, a fase Registro diz isso, e leva de volta à Qualificação.

**No registro do Livro 3**, o botão de selar cada ato fica na aba Atos, e «O que espera ação»
leva direto a ele. O cancelamento do registro vem recolhido na aba Lançar, com o mesmo formulário.

### 23.5 As telas em quadros recolhidos

Algumas telas longas não têm ordem nem fase. Nelas, cada grupo é um quadro que abre e fecha, e
o título do quadro já diz como ele está. **O que está recolhido vai junto quando se grava**, e
um campo recusado num quadro fechado abre o quadro, com o cursor nele.

**Roteiro do dia do Protesto.** Cada conduta é um quadro. Fechado, ele mostra o número, o
título, a hora limite e a situação, com o que falta. Vêm abertas as condutas atrasadas e a
primeira pendente. **Primeiro: o que ficou de antes** continua em cima, a conferência dos
títulos e o envio às Centrais ficam depois das condutas, e **O que saiu do roteiro** vem
recolhido. Os links para uma conduta, como os de **Atrasado agora**, abrem o quadro sozinhos, e o
encerramento do dia continua na última conduta, com o mesmo formulário.

**Catálogo de modelos.** Cada atribuição é um grupo recolhido, com a contagem de papéis e de
ajustes da casa. **Procurar papel** acha pelo nome e pela descrição, sem ligar para acento, e
abre os grupos em que achou. Editando um papel, só ele aparece, com **Todos os papéis** para
voltar.

**O que ficou pelo caminho.** A lista abre a tela, com um grupo por fonte e a contagem. A fonte
com item parado vem primeiro, e a primeira vem aberta. **Por onde ela olha** e **Moldar o que
fica e o que sai** ficam recolhidos no fim.

**CTP.** Cada ato é um quadro, com as pendências no título, e só o primeiro que espera alguma
coisa vem aberto. Com um ato aberto, a tela ainda passa de um monitor, porque cada ato tem mais
de vinte campos.

**Formulário do termo** (Teores, no Registro Civil). **Ver como fica** responde acima dos campos.
Os campos ficam em colunas, e a explicação de cada um em **De onde vem**. **Conferir com um
assento real**, os teores e a origem do texto ficam recolhidos.

**Telas longas do administrador.** Configurações, Importar de outro sistema, Uso de IA e
Numeração dos livros. O título de cada quadro diz como ele está, por exemplo, «ligado · guarda 5
dias», e o que espera ação vem primeiro: o aviso das Centrais sem credencial, os fornecedores
sem dados e as séries sem número. **As Configurações continuam sendo um formulário só:** **Salvar
configurações** fica à vista e grava todos os quadros acima dele; Centrais, Proteção do backup e
Revisão das transcrições têm botão próprio. O endereço abre o quadro
(`/configuracoes#cfg-centrais`), e depois de gravar a tela volta com os mesmos quadros abertos.

**Protocolo e DOI.** No **Protocolo**, os títulos com prazo vencido ou a até 5 dias úteis de vencer
ficam ao lado de **Prenotar novo título**, o mais atrasado primeiro. Os outros em aberto e o histórico
ficam recolhidos, e a busca traz o resultado no alto. Na **DOI**, o título do quadro dos meses diz
quantos devem satisfação, quantos venceram e quais ainda estão no prazo. Logo abaixo vem o mês
escolhido, com o que falta antes de **Gerar o arquivo**, e os atos parados vêm primeiro. **Como efetuar
a notificação**, no usucapião, não recolhe nada: os passos ficam em colunas.

**Telas de dinheiro, chaves e automação.** Carnê-leão e a configuração dele, NFS-e, Configurações que
cobram a equipe, Automação, Selador e Ajuda: configurar. O título de cada quadro diz como ele está, por
exemplo, «15 despesa(s) · 8 a classificar». **O título nunca mostra senha, chave, usuário, endereço,
documento ou impressão digital:** diz só se estão lá.

- **Carnê-leão:** despesa a classificar e entrada sem resposta vêm primeiro, e as outras ficam em **As
  já marcadas**. Sem pendência, abre **O mês em números**.
- **NFS-e:** **O que falta** fica em cima, o quadro de onde vem a falta abre sozinho, e **Gravar** grava
  os cinco quadros de dados, abertos ou recolhidos.
- **Configurações que cobram a equipe:** a caixa **Afirmo** fica no mesmo quadro do botão.
- **Automação:** **Situação** e **Rodar agora** ficam à vista, e **Rodadas** abre sozinha quando há
  problema em aberto.
- **Selador:** o que falta e **Testar a conexão** ficam em cima.
- **Ajuda: configurar:** o provedor em uso sem chave avisa no alto e abre **As chaves de API**.

**Protesto e consultas.** CRA pela API, Avisos de intimação, Repasses, Certidão, Certidão eletrônica,
Remessa do SIRC, ficha do processo, CPF do registrado, Modelos de atos, Livros obrigatórios, Selos
emitidos e Carga do Next Cloud SAS. O título de cada quadro diz como ele está, por exemplo, «3 aviso(s) ·
2 sem comprovante».

- **Avisos:** abre o primeiro quadro que tem o que fazer, e os botões do roteiro, como **Avisos
  entregues e comprovantes**, abrem o quadro certo.
- **Repasses:** a rotina ou o robô com erro abre sozinho.
- **Certidão:** o teor fica à vista ao lado dos dados, e só o cancelamento se recolhe.
- **Certidão eletrônica:** o que já saiu do registro vem antes de **Criar na Central**.
- **SIRC:** os botões de cada lote vêm primeiro, e o que ficou retido vem aberto.
- **Processo:** **Registrar andamento** fica à vista. A pasta abre quando tem peça, as evidências abrem
  quando a tarefa as exige, e o status, o vencimento e o responsável ficam em **Dados do processo**.
- **CPF:** cada nascimento é um quadro, e **Abrir todos** abre a lista inteira.
- **Modelos de atos:** registros e averbações ficam em duas colunas.
- **Livros obrigatórios:** o que falta vem primeiro.

**As outras telas** abrem na moldura nova, do jeito de sempre.

---

## 24. Atendimento ao cliente, rotinas e controles

**Atendimento ao cliente**

- **Portal do cliente**: cada protocolo ganha um código de acompanhamento, impresso
  no recibo e no protocolo de recepção. Com o número e o código, o cliente vê a
  situação do pedido e baixa um comprovante que leva só o essencial. Quem não tem o
  papel não consulta o protocolo de outra pessoa.
- **Avisos ao cliente (andamento)**: o consentimento do cliente, a marca de «pronto
  para retirar» e a fila. A tela não manda nada: quem manda é a rotina da automação.
- **WhatsApp**: a fila das conversas e o atendente com IA, depois de ligados pela
  administração. **Onde transcrever os áudios** é escolha do administrador, em
  **Atendente com IA**, e a opção «Neste servidor» só grava depois de uma conferência
  com um áudio de verdade.
- **Senhas: espera e atendimento**: espera, atendimento e desistências do período.
- **Ouvidoria**: o balcão, o gerente e o oficial registram as manifestações. A
  identificação de quem se manifestou só abre na ficha, e cada abertura fica na
  auditoria. **Convite para avaliar** leva à **pesquisa de satisfação**: o convite de
  um protocolo vai ao cliente, e há um link para o tablet do balcão.

**Rotinas e leituras**

- **Automação (rotinas)**: a central única das rotinas da casa. **Rodar agora** só
  marca o pedido, e a rotina roda no minuto seguinte. O gerente vê; ligar, editar e
  deixar agir sozinha é do administrador.
- **Produtividade**: o controle diário. Tempo líquido, desvio, eficiência e semana
  são calculados. O botão **Produtividade** abre em qualquer tela, para lançar rápido
  ou iniciar o cronômetro.
- **Leitura dos textos (IA)**: os apontamentos da leitura que ninguém conferiu ainda.
  **Relatório anual de IA**: a página pronta para imprimir. **O que a ajuda sabe do
  projeto** mostra o que a ajuda lê sobre o sistema, sem gastar consulta.

**Controles do oficial**

- **PLD / COAF**: a fila do COAF, só do administrador, porque as comunicações são
  sigilosas inclusive dentro da casa. O sistema seleciona, prepara e registra; **quem
  envia é a pessoa**, e o que se decide fica com ela.
- **Correções de ofício**: a escrevente ou um agente propõe, e a correção só se executa
  depois de aprovada. As abas são Propostas, Executadas, Recusadas e Falhas.
- **Painel no celular**: só do titular. Os números do dia, da semana e do mês, sem nome,
  sem CPF e sem teor.
- **Verificação em duas etapas**: cada pessoa ativa na própria conta. A tela do gestor
  mostra quem tem, quem está travado e o que se exige.
- **Corrigir dado do acervo**: só os campos liberados, para o que veio importado com erro.
- **Apostila de Haia**: vem desligada, e é o oficial quem liga. Ligada, traz os pedidos,
  o controle e a certidão. Cancelar apostila emitida é do oficial e do gerente.
- **Integrações do Protesto**: o modo e o provedor do AR digital e do boleto, sem mostrar
  segredo.
- **Agente (configurar)**: o provedor, o modelo, os tetos e as chaves. Ligar a escrita é
  um clique consciente, com o aviso ao lado.

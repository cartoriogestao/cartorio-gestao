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

### Atalhos

| Tela | Para quê |
|---|---|
| Visão geral | a primeira tela do dia: avisos, tarefas vencidas, protocolos parados, atos sem conclusão e comunicações pendentes |

### Tabelionato de Notas

| Seção | Telas | Para quê |
|---|---|---|
| Painel | Painel do tabelionato | o resumo do dia nas Notas |
| O balcão | Reconhecer firma · Autenticar cópia | os atos de balcão, com selo e etiqueta |
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
| Consulta e acervo | Indicador Real · Indicador Pessoal · CNIB (consulta, pendências, cópia local) · ONR (índice real e editais, certidões, endereços) · Atas de ocorrência · Fichas digitalizadas · Matrículas em Word | consultas, Centrais e o acervo digitalizado |
| Modelos | Modelos de atos · Modelos de documento | os textos dos atos e dos papéis do RI |
| Remessas e obrigações | Selos e emolumentos · Exportação ONR · Carga do Next Cloud SAS · CTP · DOI | o que se envia às Centrais, à Receita e às prefeituras |
| Configuração | Delegatários · Numeração das matrículas | quem assina e de onde parte a numeração |

### Protesto

| Seção | Telas | Para quê |
|---|---|---|
| O balcão | O roteiro das Centrais · Títulos · Certidões · Instrumentos | o roteiro diário e a ficha de cada título |
| O dia da CRA | Remessa da CRA · Imagens dos títulos · Avisos e editais · Desistências · A protestar · Retorno à CRA · CRA pela API | os arquivos da CRA, na ordem do dia |
| O dia da CENPROT | Pendências da CENPROT · Intimação Digital · Chave do CENPROT | anuências, cancelamentos, certidões e intimação eletrônica |
| Modelos | Modelos dos documentos | os papéis do Protesto |

### Registro Civil das Pessoas Naturais

| Seção | Telas | Para quê |
|---|---|---|
| O balcão | Assentos · Importar pré-cadastros · Averbações · Certidões · Folhas de segurança · Pedidos da Central · Documentos avulsos | o dia a dia do civil |
| Nascimento | Novo registro · Digitar já lavrado · Teores · Registro tardio · Gêmeos · CPF do registrado | o registro de nascimento e as formas especiais |
| Casamento | Registro · Digitar já lavrado · Habilitação → Edital de proclamas → Enviar ao e-Proclamas → Prontas para casar · Teores | a habilitação na ordem da lei, e o assento |
| Óbito | Novo registro · Digitar já lavrado · Teores · Comunicações mensais · O que falta perguntar | o óbito e as comunicações que ele gera |
| Assento já lavrado | Retificação e suprimento · Atos sem checklist · Termos a escrever · Termos a digitalizar · Informações importadas · CPF nos assentos antigos · Matrículas · Conferência da filiação | o que se faz depois do registro |
| Comunicações e remessas | O que comunicar hoje · SIRC · FUNAI · Carga da CRC · Anotações devidas · Anotação da CRC · IBGE | as comunicações obrigatórias, cada uma com o seu prazo |
| Modelos | Modelos dos documentos | os papéis do civil |

### RCPJ e RTD

| Seção | Telas | Para quê |
|---|---|---|
| O balcão | Títulos apresentados (RTD e RCPJ) · Etiquetas de selos externos · Central ONRTDPJ | protocolo, qualificação e a fila da Central |
| Registro já lavrado | Registros lavrados (RCPJ e RTD) · Últimos atos · Certidões de inteiro teor | consulta e certidão |
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
| Dinheiro | Caixa · Protocolo geral · Protocolos parados · Depósito prévio · Recibos · Emolumentos · Selos emitidos | o caixa e o protocolo, que são um só trilho; o razão dos selos |
| Atendimento | Atendimento / senhas · O que ficou pelo caminho · Envios às Centrais · Caixas para o visto · Relatório de erros · Rascunhos · Consultar fraudes · Relatórios | o acompanhamento do dia e o que não terminou |
| A casa | Atenção para fraudes · Checklists · Obrigações recorrentes · LGPD e governança · TI e infraestrutura · Auditoria · Integridade | governança e controle interno |
| Ajuda | Ajuda do sistema · Avisos da serventia · Problemas relatados · Base de conhecimento | dúvidas, avisos e relato de problemas |
| Modelos | Modelos dos documentos · Modelos do caixa | o catálogo geral dos papéis |
| Configuração | Configurações · Usuários · Selador · Rede / acesso · Correções e atualizações · Ajuda (configurar) | a administração da instalação (seções 3 e 19) |

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

**Depósito prévio** registra o valor adiantado: o depósito é recebimento;
usar o saldo não é receita nova; devolver gera saída, com motivo.

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
  **CTP — prefeituras** e **Selos e emolumentos** também ficam em Remessas e
  obrigações.
- **Delegatários** e **Numeração das matrículas** são configuração restrita.

---

## 10. Protesto de títulos

O módulo pode estar fechado para o balcão (seção 3.2). Seções: O balcão; O dia
da CRA; O dia da CENPROT; Modelos.

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
cancelamento continua na ficha do título.

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

---

## 13. Livros, termos e acervo

Menu **Livros e acervo**:

- **Livros e termos**: séries, livro aberto, folha e próximo número. Abre livro
  (o número é o seguinte da série, não se digita), emite **termos de abertura e
  encerramento** em `.odt`, registra faces inutilizadas, encerra livro.
- **Encerramento diário**: fecha o dia dos livros de protocolo e mostra atrasos.
- **Numeração dos livros**: configuração restrita — **não altere contador para
  corrigir um ato isolado**.
- **O que falta informar**: seção 17.
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
  montar; corpo vazio não se grava.
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
| ONR | RI | ONR — índice real e editais; endereços a conferir; Exportação ONR | envia indicador real e edital do usucapião; propõe endereços lidos do teor para você conferir |
| Next Cloud SAS (ONR) | RI | Carga do Next Cloud SAS | prepara e confere a carga do indicador pessoal e das imagens; quem transmite são os programas do ONR |
| CNIB | RI | CNIB — indisponibilidade; o que espera seu okay | mantém a cópia local, avisa quando nome ou documento bate e **prepara** a averbação, que espera o okay. Veja a data da última atualização antes de concluir que não há restrição |
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

**Robô do malote.** Em **Automação**, o processo «Malote — ciência diária e cadastro» entra no Malote Digital às 8h dos dias úteis com usuário e senha, sem certificado. O login se guarda na tela **Malote: login e código de dois fatores**, com o cofre aberto; é a mesma tela onde se digita o código quando o malote o pede.

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

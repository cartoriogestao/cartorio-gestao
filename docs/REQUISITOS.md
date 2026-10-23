# O que é preciso para operar o sistema

Esta lista reúne os programas, aparelhos e cadastros de que o Cartório Gestão
depende, separados entre o que é **obrigatório** e o que é preciso **só para
uma função**. A instalação passo a passo está em
[`INSTALACAO.md`](INSTALACAO.md), e o uso do dia a dia, em
[`MANUAL.md`](MANUAL.md).

## Resumo

| Item | Onde | Para quê | Obrigatório? |
|---|---|---|---|
| Windows 10 ou 11 (com PowerShell 5.1) | servidor | roda o sistema e a tarefa que o sobe com o Windows | sim |
| Python 3.11 ou mais novo | servidor | executa o sistema (o instalador cria um Python próprio) | sim |
| Pacotes Python de `requirements.txt` | servidor | instalados pelo instalador | sim |
| PostgreSQL (a referência usa o 18) | servidor | o banco de dados — desde a 3.7.0 | sim |
| Navegador atual (Chrome, Edge ou Firefox) | balcão e servidor | é a tela do sistema | sim |
| LibreOffice | servidor | abre e converte os papéis `.odt` em PDF | sim, para imprimir em PDF |
| Google Chrome ou Microsoft Edge | servidor | gera em PDF os papéis desenhados em HTML (folha do livro, prévia de certidão) | sim, para esses papéis |
| Aparelho selador do Tribunal | rede local | selo eletrônico de fiscalização | sim, onde o selo é obrigatório |
| Impressora térmica de etiquetas | balcão | etiqueta de firma, autenticação e registro | para essas etiquetas |
| Token A3 (ICP-Brasil) + programa do fabricante | máquina de quem assina | assinatura digital do delegatário, carga da CRC, CCN | para assinar |
| Serviço local de assinatura (`a3_servico_local.py`) | máquina do token | faz a ponte entre o sistema e o token | para assinar |
| Extensão «CG CCN Assistente» | navegador de quem envia ao CCN | envio de cadastros e consulta ao CCN do e-Notariado | para o CCN |
| Leitor de PDF | balcão | abre os papéis em PDF para imprimir | sim (vem no navegador) |
| Scanner | balcão | digitalização de fichas e documentos | para digitalizar |
| Credenciais das Centrais | cadastro de cada Central | envio e consulta às Centrais | para cada integração |
| Chave de API de um provedor de IA | contratada pela serventia | ajuda do sistema com IA | não |

## 1. O servidor

### Windows e Python
- **Windows 10 ou 11**, com o **PowerShell 5.1** que já vem no Windows. O
  instalador usa o Agendador de Tarefas para subir o sistema junto com o
  Windows, sem precisar de alguém logado.
- **Python 3.11 ou mais novo.** O instalador procura um Python na máquina e,
  se não achar, tenta instalar o Python 3.12 pelo `winget`. A partir dele cria
  um Python **privado do sistema** (`runtime`, na pasta de dados), que não
  interfere em outros programas.
- **Pacotes Python**, instalados pelo instalador a partir de
  [`requirements.txt`](../requirements.txt):

| Pacote | Para quê |
|---|---|
| Flask e waitress | o servidor web |
| Pillow | converte fichas digitalizadas (TIFF) para exibir no navegador |
| pypdfium2 | converte a ficha de firma em PDF para imagem |
| segno | gera o QR do selo |
| asn1crypto | lê o arquivo `.p7s` que volta assinado |
| PyKCS11 | fala com o driver do token A3, sempre num processo separado |
| lxml | canonicalização XML da assinatura da carga da CRC |
| cryptography | cifra o arquivo do SIRC e confere a assinatura das atualizações |
| PyMuPDF | lê PDF nas intimações em lote do Protesto e nas imagens enviadas ao ONR |

### LibreOffice — papéis em `.odt` e PDF
Certidões, termos, recibos, traslados e fichas saem em **`.odt`** (formato
aberto, editável). Para imprimir, o sistema converte o mesmo `.odt` em **PDF**
com o LibreOffice, sem redesenhar o papel.

- Instale o **LibreOffice** (versão estável atual) no servidor, no caminho
  padrão (`C:\Program Files\LibreOffice`). O sistema também o acha pelo
  `PATH`.
- Sem o LibreOffice, os papéis continuam saindo em `.odt`, mas o botão de
  imprimir não entrega PDF. O formato padrão (PDF ou `.odt`) pode ser
  escolhido em **Configurações**.
- Nos computadores do balcão, para abrir ou ajustar um `.odt` baixado, use o
  LibreOffice ou outro editor que leia ODT.

### Chrome ou Edge — papéis desenhados em HTML
Alguns papéis, como a folha do livro e a prévia da certidão, são desenhados em
HTML e convertidos em PDF pelo navegador, sem janela. O sistema procura o
**Google Chrome** ou o **Microsoft Edge** nos caminhos padrão e no `PATH` do
Windows. O Edge já vem no Windows 10 e 11. Se o navegador estiver em outro
lugar, o caminho pode ser gravado na configuração `chrome_caminho` (tabela
`settings`).

### O banco de dados: PostgreSQL
- **Desde a versão 3.7.0 o banco é o PostgreSQL** (a instalação de referência
  usa o PostgreSQL 18, só em `localhost`). O sistema não roda mais no SQLite:
  sem a variável `CG_PG_DSN`, ele recusa abrir o banco.
- O serviço lê duas variáveis, postas no `iniciar_servidor_servico.cmd` da
  pasta de dados: `CG_PG_DSN` (ex.: `host=127.0.0.1 port=5434 user=cg
  dbname=cartorio`, **sem senha**) e `CG_PG_SCHEMA` (o schema da casa). A
  senha do papel fica num `pgpass.conf` protegido, e o backup usa o `pg_dump`
  da pasta indicada em `CG_PG_BIN`.
- **O instalador ainda não instala nem configura o PostgreSQL**: isso é feito
  à parte, antes do primeiro acesso. Senha SCRAM, `pgpass` e papel sem
  superusuário estão em [`SEGURANCA_REDE.md`](SEGURANCA_REDE.md#o-postgresql-da-casa)
  e em [`SEGURANCA_IMPLANTACAO.md`](SEGURANCA_IMPLANTACAO.md); a passagem de
  uma instalação antiga (SQLite) para o PostgreSQL, em
  [`ROTEIRO_DA_VIRADA.md`](ROTEIRO_DA_VIRADA.md).

### Rede
- Porta **TCP 8765**: a aplicação. **UDP 8766**: a descoberta automática do
  servidor pelos computadores do balcão. O instalador libera as duas no
  Firewall do Windows, só para a rede local.
- **Não exponha a porta 8765 à internet.** Para acesso de fora, use VPN.

## 2. Os computadores do balcão

- Um **navegador atual**: Chrome, Edge ou Firefox. O atalho abre o navegador
  padrão do Windows.
- O atalho criado por `INSTALAR_CLIENTE.cmd`, que acha o servidor sozinho.
  Os computadores do balcão não precisam de Python.
- **Impressora térmica de etiquetas**, para as etiquetas de reconhecimento de
  firma e autenticação (padrão 100 × 30 mm) e de registro do RTD/PJ (padrão
  90 × 40 mm). As medidas e margens se ajustam numa tela do sistema, sem
  mexer no código.
- **Scanner**, para digitalizar fichas e documentos. Para o envio de imagens
  ao ONR, o padrão nacional é TIFF Grupo 4, 200 dpi.

## 3. Selo eletrônico

O selo de fiscalização é pedido a um **aparelho selador** instalado na rede
local da serventia, fornecido pelo Tribunal de Justiça do estado ou por quem
ele indicar. É preciso:

- o **endereço** do aparelho, informado em **Configurações → Serventia**;
- o **usuário e a senha** da serventia no aparelho, em **Administrativo →
  Selador**. Eles ficam num arquivo `.cred` fora do banco;
- conferir a **impressão digital do certificado** do aparelho com quem o
  instalou: o sistema fixa o certificado em vez de ignorá-lo.

> O selador e os caminhos de selo seguem o padrão do estado em que o sistema
> nasceu (*norma estadual*). Em outro estado, confira o contrato do selador
> local antes de usar o selo automático.

## 4. Assinatura digital (certificado A3)

A assinatura do delegatário (instrumentos, carga da CRC, CCN) usa
**certificado ICP-Brasil em token ou cartão A3**. O sistema **nunca guarda a
chave nem o PIN** e nunca carrega o driver do token dentro do servidor, porque
carregar o driver ali pode derrubar o sistema inteiro. A assinatura acontece
num processo separado, na máquina onde o token está plugado.

É preciso, nessa máquina:

1. **O token ou cartão A3** e o **programa do fabricante**, que instala o
   driver PKCS#11. Os drivers que o sistema já reconhece:

   | Programa do fabricante | Driver |
   |---|---|
   | SafeNet Authentication Client (Thales/Gemalto) | `eTPKCS11.dll` |
   | Thales/Gemalto IDPrime (IDGo 800) | `IDPrimePKCS1164.dll` / `IDPrimePKCS11.dll` |
   | SafeSign IC (A.E.T.) | `aetpkss1.dll` |
   | Watchdata | `WDPKCS64.dll` / `WDPKCS.dll` |

   Outro driver pode ser indicado pela variável `CG_A3_DRIVER` ou pelo arquivo
   `a3_local.json` na pasta de dados: `{"driver": "C:/Windows/System32/x.dll"}`.

2. **O serviço local de assinatura**, que escuta **só em 127.0.0.1:8766**,
   nunca na rede, e pede o PIN na hora de cada assinatura:

   ```bat
   "%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" "C:\Program Files\CartorioGestao\a3_servico_local.py"
   ```

   O endereço `/saude` desse serviço mostra quais drivers ele encontrou.

O sistema também **confere** um `.p7s` devolvido assinado: quem assinou e se
o documento é exatamente o que a serventia emitiu. Ele **não afirma** que a
assinatura é juridicamente válida, porque isso exige a cadeia da ICP-Brasil e
a lista de revogação.

## 5. A extensão do CCN (e-Notariado)

O envio de cadastros ao CCN e a consulta à base nacional acontecem **de dentro
da aba do portal do e-Notariado**, com a sessão que a própria pessoa abriu. A
extensão faz a ponte entre essa aba e o sistema.

- Fica em `ccn_assistente/extensao` (Chrome ou Edge, Manifest V3).
- Para instalar: abra `chrome://extensions` ou `edge://extensions`, ligue o
  **Modo do desenvolvedor**, clique em **Carregar sem compactação** e escolha
  a pasta `ccn_assistente\extensao` da instalação.
- A consulta exige o **serviço local de assinatura** no ar e o token plugado.
- A chave da API do CCN e o identificador do cartório são fornecidos pelo
  Colégio Notarial. Digitados no painel da extensão, ficam só na memória do
  navegador.

## 6. Credenciais das Centrais

Cada integração exige o cadastro da serventia na Central e a credencial que
ela fornece. Tudo se grava em **Configurações → Centrais**, num arquivo
`.cred` por Central, fora do banco e fora do backup. O ambiente (homologação
ou produção) faz parte da credencial. Comece pela homologação quando a Central
oferecer uma.

| Central | Atribuição | Forma da credencial |
|---|---|---|
| CRA (SOAP) e CENPROT/Resolve | Protesto | usuário e senha; chave de API na Intimação Digital |
| ONR (SAEC, Indicador Real, Next Cloud SAS) | Registro de Imóveis | par de credenciais da API |
| CNIB | Registro de Imóveis | conforme o cadastro da Central |
| ON-RCPN (e-Proclamas e Certidão Eletrônica) | Registro Civil | token |
| CRC Nacional | Registro Civil | certificado A3 com PIN na hora, sem arquivo `.cred` |
| SIRC | Registro Civil | usuário e senha |
| ONRTDPJ | RTD e RCPJ | token gerado no portal da Central |
| CENSEC e CCN (e-Notariado) | Notas | chave de API do Colégio Notarial (CCN pela extensão) |

O que cada Central aceita, e as armadilhas conhecidas de cada contrato, está em
[`decisoes/`](decisoes/README.md).

## 7. Inteligência artificial (opcional)

A ajuda do sistema pode consultar um provedor de IA escolhido pela serventia:
DeepSeek, Anthropic (Claude), OpenAI (GPT) ou xAI (Grok). Para isso, é preciso
uma **chave de API** contratada com o provedor, gravada em **Configurações**,
fora do banco. Sem chave, o sistema funciona normalmente, só sem essa ajuda.
Por padrão, CPF, CNPJ e outros dados pessoais são mascarados antes de qualquer
envio.

## 8. Backup

- Configure em **Configurações** a pasta de backup e, de preferência, uma
  **segunda cópia em outro disco** ou numa pasta sincronizada com a nuvem.
- Os arquivos `*.cred` e o `secret.key` **não** vão no backup do banco, de
  propósito. Guarde-os à parte, em local seguro, para reinstalar o servidor.

## 9. Para quem vai programar

- O mesmo Python 3.11+ e os pacotes de `requirements.txt`; para os testes,
  `pytest` e `pytest-xdist`. Para gerar o instalador, `requirements-build.txt`
  (PyInstaller).
- Veja [`ARQUITETURA.md`](ARQUITETURA.md), [`AGENTES.md`](AGENTES.md) e
  [`decisoes/`](decisoes/README.md).
- Para conhecer o sistema ou testar uma alteração sem risco, use o sandbox de
  demonstração (`INICIAR_SANDBOX.cmd`): veja o capítulo 22 do
  [`MANUAL.md`](MANUAL.md#22-o-sandbox-conhecer-e-testar-sem-risco).

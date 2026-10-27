# Instalação do Cartório Gestão

> Versão curta. O [manual geral](MANUAL.md) traz a instalação, a configuração
> e o panorama de todas as telas, e a lista completa do que é preciso
> (LibreOffice, navegador, selador, token A3, extensão do CCN, credenciais)
> está em [`REQUISITOS.md`](REQUISITOS.md).

Um computador da serventia é o **servidor**: guarda o banco e os documentos e
atende os demais pela rede local. Os computadores do balcão só usam o
navegador.

## 1. O servidor

1. Copie a pasta do sistema para o servidor (qualquer lugar temporário).
2. Execute **`INSTALAR_SERVIDOR.cmd`** e confirme a permissão de Administrador.
   O instalador:
   - copia o programa para `C:\Program Files\CartorioGestao`;
   - cria a pasta de dados em `C:\ProgramData\CartorioGestao`;
   - prepara um Python **privado** do sistema (`runtime`) — se não houver
     Python 3.11+ na máquina, tenta instalar o 3.12 pelo `winget`;
   - libera no Firewall do Windows a porta da aplicação (TCP **8765**) e a da
     descoberta automática (UDP **8766**), para a sub-rede local;
   - registra a tarefa `CartorioGestaoServidor`, que sobe o servidor junto com
     o Windows, sem depender de alguém logado.
3. Ao final, o navegador abre o sistema.

Se algo falhar, **`DIAGNOSTICAR_INSTALACAO.cmd`** mostra o motivo, e o registro
fica em `C:\ProgramData\CartorioGestao\logs`.

> **Depois de instalar, endureça o servidor:** permissões da pasta de dados,
> Python do serviço fora do perfil de uma pessoa, papel do banco sem
> superusuário, firewall por perfil, rotinas e a chave que assina as
> atualizações. O roteiro, com os comandos e a conferência de cada item, é
> [`SEGURANCA_IMPLANTACAO.md`](SEGURANCA_IMPLANTACAO.md).

### A pasta de dados

| | |
|---|---|
| `iniciar_servidor_servico.cmd` | o lançador do serviço, com o endereço do banco (`CG_PG_DSN`, `CG_PG_SCHEMA`) |
| `arquivos\` | documentos anexados e digitalizações |
| `backups\` | backups automáticos e manuais |
| `updates\` | pacotes aplicados e cópias para voltar atrás |
| `secret.key` | a chave de sessão do Flask — não copie para outro lugar |
| `*.cred` | credenciais do selador, das Centrais e dos provedores de IA |

Outra pasta pode ser usada definindo `CARTORIO_GESTAO_DATA` (ver
`.env.example`).

**O banco não fica nesta pasta: é o PostgreSQL** (desde a 3.7.0), num
serviço próprio do servidor. O instalador ainda não o instala — veja
[`REQUISITOS.md`](REQUISITOS.md#o-banco-de-dados-postgresql) antes do
primeiro acesso.

## 2. O primeiro acesso

1. Na primeira vez, o sistema pede para criar o **administrador**
   (`/setup`). Cada pessoa da serventia deve ter a sua própria conta depois.
2. Em **Configurações → Serventia**, preencha os dados da sua serventia: nome,
   CNS, CNPJ, endereço, CEP, cidade, UF, titular e substituto(a), brasão e o
   endereço do aparelho selador. **O código não traz dado de serventia
   nenhuma** — papéis e remessas saem com o que estiver aqui.
3. Em **Configurações**, confira a data da tabela de custas em vigor. Os
   feriados locais (estaduais e municipais) contam nos prazos, mas ainda não
   têm tela própria: ficam na configuração `ri_feriados_locais`, com uma data
   `AAAA-MM-DD` por linha (veja o [manual](MANUAL.md), seção 3).

> **Instalação que já tinha os dados dentro do código** (versões antigas): rode
> uma vez `tools\migrar_settings_serventia_b0.py`. Ele lê o perfil local
> `serventia_local_atual.json` da pasta de dados, grava só as chaves que
> estiverem em branco e faz backup do banco antes.

## 3. Os computadores do balcão

Execute **`INSTALAR_CLIENTE.cmd`** uma vez em cada computador (ou baixe o
instalador pela página **Rede / acesso** do sistema). Ele cria o atalho
**Cartório Gestão**, que acha o servidor sozinho: tenta o último endereço que
funcionou e, se não der, procura na rede pela descoberta automática. Os
clientes não precisam de Python nem de IP fixo.

Se os computadores estiverem em redes separadas (VLAN, Wi-Fi de visitantes,
isolamento de clientes), quem administra a rede precisa liberar o tráfego
entre eles. No servidor, **`REPARAR_REDE.cmd`** refaz as regras do firewall,
reinicia o servidor e mostra os endereços encontrados.

**Não exponha a porta 8765 à internet.** Para acesso de fora, use VPN e HTTPS
administrados por um profissional de TI.

## 4. Selo eletrônico e Centrais

- **Selador.** O endereço do aparelho fica em Configurações; o usuário e a
  senha, em **Administrativo → Selador**, gravados em `selador.cred`. O
  certificado do aparelho é **fixado** (conferido pela impressão digital), e
  não ignorado.
- **Centrais** (CRA, CENPROT, ONR, ON-RCPN, ONRTDPJ, SIRC, CNIB, Resolve…):
  **Configurações → Centrais**. Cada credencial vai para o seu `.cred`, com o
  ambiente (homologação ou produção) fazendo parte da chave. Comece pela
  homologação quando a Central oferecer uma.
- **Certificado A3.** A assinatura com token A3 acontece **fora** do processo
  do servidor: carregar o driver PKCS#11 dentro dele pode derrubá-lo.

## 5. Atualizações

As versões novas chegam como pacotes **`.cgu`**, acompanhados do SHA-256.

1. Entre como **ADMIN** e abra **Atualizações**.
2. Selecione o `.cgu` e cole o SHA-256 informado.
3. Clique em **Validar, fazer backup e atualizar**.

O sistema confere o SHA-256 do pacote e de cada arquivo, recusa caminho que
saia da pasta de instalação, faz backup do banco e dos documentos, guarda o
programa anterior, aplica, reinicia e testa `/saude` — e **volta sozinho** à
versão anterior se o servidor novo não responder. O banco só recebe migrações
que acrescentam (nunca apagam coluna nem tabela).

## 6. Backup

- Configure em **Configurações** a pasta de backup e, se houver, uma segunda
  cópia (espelho) em outro disco.
- Os `*.cred` e o `secret.key` **não** vão no backup do banco, de propósito:
  guarde-os à parte, em local seguro, para reinstalar o servidor.

A sincronia dos problemas com o desenvolvimento tem manual próprio: [`SINCRONIA_DOS_PROBLEMAS.md`](SINCRONIA_DOS_PROBLEMAS.md).

## 7. Desinstalar

Pelo **Configurações do Windows → Aplicativos instalados**. O desinstalador
pergunta se os dados devem ser apagados; o padrão é **preservá-los**.

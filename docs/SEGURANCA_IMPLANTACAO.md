# Segurança da implantação — o que o servidor e a casa configuram

> Guia para quem instala e mantém o Cartório Gestão numa serventia. Nada do
> que está aqui exige mexer no código: é configuração do Windows, do
> PostgreSQL e da rotina da casa. Cada item diz **o risco**, **o que fazer** e
> **como conferir** — e a regra é sempre a mesma: **meça antes de mudar, e meça
> de novo depois.** As recomendações saíram de uma revisão de segurança feita
> sobre uma instalação real em outubro de 2026 (versão 3.7.0); o que era código
> entrou na 3.7.1, e o que é implantação está aqui.
>
> Complementos: [`SEGURANCA_REDE.md`](SEGURANCA_REDE.md) (senha do banco,
> HTTPS, `/saude`), [`BACKUP.md`](BACKUP.md) (a cifra do backup) e
> [`INSTALACAO.md`](INSTALACAO.md).

## 0. O princípio

O servidor do sistema costuma ser **um computador da própria serventia**, com
gente logada nele, programas de terceiros, pastas compartilhadas e o sistema
antigo ao lado. Quase tudo o que a revisão achou de grave vinha daí: não do
código, mas de **quem pode escrever onde**. Um usuário comum da máquina que
consiga gravar um arquivo na pasta do programa, no Python do serviço ou na
pasta de preparação das atualizações passa a executar código como o serviço —
sem precisar de senha nenhuma do sistema.

Por isso a ordem deste guia é: pastas e contas → banco → rede → rotinas →
atualizações → backup → usuários do sistema → o que é de terceiros.

## 1. Pastas e contas do Windows

### 1.1 A pasta de dados (`C:\ProgramData\CartorioGestao`)

**O risco.** `C:\ProgramData` deixa, por herança, qualquer usuário da máquina
**criar arquivos** em toda subpasta. Dentro da pasta de dados moram o
`runtime` (o Python privado do serviço: um `.pth` plantado em
`runtime\Lib\site-packages` roda como SYSTEM na próxima subida), a pasta
`updates\staged` (onde a atualização é preparada antes de ser aplicada), o
banco, os documentos e os segredos.

**O que fazer** (sessão de administrador; o serviço pode ficar no ar):

```
icacls C:\ProgramData\CartorioGestao /inheritance:d
icacls C:\ProgramData\CartorioGestao /remove:g *S-1-5-32-545
icacls C:\ProgramData\CartorioGestao /grant "*S-1-5-32-545:(OI)(CI)RX"
```

Isto desliga a herança copiando as permissões, tira de **Usuários** o direito
de criar e grava de volta só **leitura e execução**. SYSTEM
(`*S-1-5-18`) e Administradores (`*S-1-5-32-544`) continuam com controle
total — são eles que o serviço e o instalador usam. Os SIDs numéricos servem
em qualquer idioma do Windows. **Nenhuma conta de pessoa** deve ter permissão
própria na pasta: se a sua tiver, tire (`/remove:g <conta>`).

Antes de qualquer `icacls`, salve a permissão atual para poder voltar:
`icacls C:\ProgramData\CartorioGestao /save antes.acl /T /C`
(volta com `icacls C:\ProgramData /restore antes.acl`).

**Como conferir.** Numa sessão **sem** elevação, tente criar um arquivo em
`runtime\Lib\site-packages`, em `updates\staged` e na raiz da pasta de dados:
os três têm de ser **negados**. O servidor tem de continuar respondendo em
`/saude` e o backup do dia tem de sair.

### 1.2 Os segredos

`secret.key`, `*.cred`, `pgpass.conf`, `*.pfx` e `*.pem` da pasta de dados são
só de SYSTEM, Administradores e da conta do serviço. O sistema aplica essa
permissão **ao subir e sempre que regrava um deles** (desde a 3.7.1; antes, só
na subida). Se o log avisar de permissão, à mão:

```
icacls <arquivo> /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F
```

### 1.3 O Python do serviço

**O risco.** O `runtime` é um ambiente virtual, e ele aponta para o Python de
onde foi criado. Se o Python foi instalado **no perfil de uma pessoa**
(a pasta `AppData\Local\Programs\Python` dentro do perfil dela), o serviço executa um
interpretador que **qualquer processo dessa pessoa altera** — o `icacls` da
pasta de dados não alcança isso.

**O que fazer.** Instalar o Python 3.11+ «para todos os usuários» (fica em
`C:\Program Files\Python3xx`) e recriar o `runtime` com o instalador numa
janela de manutenção (o serviço para e volta). Em instalação nova, basta ter
esse Python antes de rodar `INSTALAR_SERVIDOR.cmd`.

**Como conferir.** `type C:\ProgramData\CartorioGestao\runtime\pyvenv.cfg`:
a linha `home =` tem de apontar para `C:\Program Files\...`, nunca para a
pasta de perfil de alguém (`Users\<nome>\AppData\...`).

### 1.4 As outras pastas do sistema

| pasta | quem precisa | o que tirar |
|---|---|---|
| `C:\Program Files\CartorioGestao` (o programa) | SYSTEM e Administradores escrevem; Usuários leem | qualquer «Modificar» de Usuários ou de conta de pessoa |
| os binários do PostgreSQL | só leitura e execução para quem não é administrador | «Usuários autenticados: Modificar» — quem troca o `postgres.exe` é dono do banco |
| a pasta das cópias de segurança | SYSTEM, Administradores e a conta que roda o backup | leitura por Usuários: o backup é o banco inteiro |
| a pasta de onde as **rotinas** rodam (ver §4) | só administradores escrevem | qualquer grupo ou SID sem nome com Modificar |

### 1.5 Contas e compartilhamentos

- **Conta Convidado desativada:** `net user Convidado /active:no`
  (`net user Guest /active:no` em Windows em inglês).
- **Nenhum compartilhamento com «Todos: controle total».** Liste com
  `Get-SmbShare | Get-SmbShareAccess` e troque «Todos» pelos grupos certos,
  com o mínimo de direito. Compartilhar `C:\Users` ou a pasta do programa é
  entregar a máquina.
- **SIDs sem nome** (`S-1-5-21-…` que o Windows não traduz) numa pasta do
  sistema são contas de máquinas ou instalações que já não existem: tire-os.
- **Grupos de ferramentas de IA e de desenvolvimento** (sandboxes de agentes,
  workers de editores que rodam no logon) não devem ter escrita na pasta de
  onde o pacote de atualização sai — e não devem rodar no servidor da
  produção.

## 2. O banco de dados (PostgreSQL)

### 2.1 Senha

O papel do sistema entra com senha SCRAM, guardada num `pgpass.conf` protegido
e nunca dentro do `CG_PG_DSN`. O passo a passo, com os comandos, está em
[`SEGURANCA_REDE.md`](SEGURANCA_REDE.md#o-postgresql-da-casa). O banco escuta
só em `localhost`, e a porta dele não tem regra no firewall.

### 2.2 O papel do sistema não é superusuário

**O risco.** Instalações feitas com o PostgreSQL portátil nascem com um papel
só (`cg`), que é **superusuário** do cluster e é o que o servidor, o backup e
toda ferramenta usam. Quem tiver a senha dele — ou o `pgpass` — manda no
cluster inteiro, lê a senha de todos os papéis e o comando de todas as
conexões.

**O que o sistema precisa de verdade:** ser **dono** do banco e dos schemas
(cria tabela, acrescenta coluna, cria gatilho e índice) e poder criar as
extensões confiáveis `pg_trgm` e `unaccent` (o dono do banco pode, desde o
PostgreSQL 13). Nada disso exige superusuário.

**O que fazer, nesta ordem** — e nunca na ordem inversa, senão o cluster fica
sem administrador:

1. Criar um superusuário **reserva**, com senha longa guardada fora da máquina
   (pendrive do oficial, cofre de senhas):
   `CREATE ROLE cg_admin SUPERUSER LOGIN PASSWORD '<senha longa>';`
2. Só então: `ALTER ROLE cg NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS;`
3. Reiniciar o serviço do sistema e conferir que ele sobe, lavra um ato de
   teste no sandbox e que o backup do dia sai.

Se alguma operação parar depois disso, a volta é uma linha, entrando como
`cg_admin`: `ALTER ROLE cg SUPERUSER;` — e o motivo vira relato para o
desenvolvimento.

### 2.3 A auditoria é imutável

Desde a 3.7.1 cada linha de `audit_logs` leva o hash da anterior e o seu
(corrente de hash, feita por gatilho no banco, válida para todo caminho que
grava na tabela), e a conferência da casa (`compliance`, regra
`AUDITORIA_CADEIA`) acusa linha apagada, editada ou gravada fora da corrente.
O que a casa acrescenta, no servidor, é **recusar alteração e exclusão** na
própria tabela — nenhum código do sistema faz UPDATE, DELETE ou TRUNCATE nela:

```sql
CREATE OR REPLACE FUNCTION producao.cg_auditoria_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $f$
BEGIN
  RAISE EXCEPTION 'audit_logs e imutavel: a linha % nao se altera nem se apaga',
                  COALESCE(OLD.id, 0);
  RETURN NULL;
END $f$;
CREATE OR REPLACE TRIGGER audit_logs_imutavel
  BEFORE UPDATE OR DELETE ON producao.audit_logs
  FOR EACH ROW EXECUTE FUNCTION producao.cg_auditoria_imutavel();
CREATE OR REPLACE TRIGGER audit_logs_imutavel_truncate
  BEFORE TRUNCATE ON producao.audit_logs
  FOR EACH STATEMENT EXECUTE FUNCTION producao.cg_auditoria_imutavel();
```

`producao` é o schema do sistema (o de `CG_PG_SCHEMA`; troque se o seu for
outro). **Como conferir:** um `DELETE` de uma linha qualquer tem de ser
recusado com a mensagem acima; e `SELECT tgname FROM pg_trigger WHERE
tgrelid = 'producao.audit_logs'::regclass` tem de listar os dois gatilhos e o
`audit_logs_cadeia` do sistema.

## 3. Rede e firewall

- **Perfis.** As regras do sistema (porta da aplicação, descoberta UDP e, se
  houver, o sandbox) valem só nos perfis **Privado** e **Domínio**. Se a
  interface da serventia estiver em «Pública», corrija o perfil
  (`Set-NetConnectionProfile -InterfaceAlias '<nome>' -NetworkCategory
  Private`) antes de mexer nas regras — invertido, o balcão perde o servidor.
- **Origem.** Se ninguém usa o sistema de fora da serventia, limite as regras
  à sub-rede local (`Set-NetFirewallRule -DisplayName '<regra>'
  -RemoteAddress LocalSubnet`). Se há VPN (Tailscale ou outra) e alguém
  trabalha por ela, **não** limite: o acesso remoto é decisão da casa, e a
  proteção certa para ele é o HTTPS de `SEGURANCA_REDE.md`.
- **Regras genéricas.** Apague regras de firewall por programa que liberem
  «`python.exe` em qualquer porta» — elas abrem o que o Python do perfil de
  alguém quiser escutar.
- **Descoberta automática só enquanto é preciso.** O atalho criado por
  `INSTALAR_CLIENTE.cmd` guarda o último endereço que funcionou e só procura
  na rede (UDP 8766) quando ele falha — e a procura aceita **a primeira
  resposta que chega**, de quem quer que seja. Depois que todos os
  computadores do balcão entraram ao menos uma vez, desligue a descoberta em
  **Configurações** (`discovery_enabled`); se o servidor mudar de endereço,
  religue-a por um dia.
- **Portas do banco e do sandbox** não têm regra para a rede.

## 4. Rotinas, tarefas agendadas e a pasta do projeto

**O risco.** Rotinas diárias (backup, conferência, envios automáticos) que
rodam a partir de uma pasta de trabalho — `Downloads`, o perfil de alguém,
uma pasta sincronizada com a nuvem — executam **o que estiver lá no momento**.
Quem escreve nessa pasta escreve na rotina da serventia.

**O que fazer.**

- As rotinas rodam de uma pasta que **só administradores escrevem** (por
  exemplo `C:\ProgramData\CartorioGestao\rotinas`), com `%~dp0` e
  `%PROGRAMDATA%` nos `.cmd` em vez de caminho absoluto.
- A conta que as executa é uma conta de serviço ou a conta do operador do
  backup — **sem** direito de escrita na pasta de onde rodam. Rodar como
  SYSTEM só se nada da rotina depende do perfil de uma pessoa (o espelho numa
  nuvem montada no perfil, por exemplo, deixa de funcionar como SYSTEM).
- **Nenhuma tarefa de terceiro** (worker de editor de código, agente de IA
  que religa no logon) com a pasta do sistema ou do pacote como área de
  trabalho, na máquina da produção.
- Tarefas órfãs (temporárias, de testes antigos) saem:
  `Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' }` e exporte
  antes de apagar (`Export-ScheduledTask`).

**Como conferir, por mês:** `Get-ScheduledTask` filtrando pelo nome do
sistema — para cada rotina, quem roda, de onde e com que nível.

## 5. Atualizações e a chave que as assina

- O pacote `.cgu` é **assinado** com a chave privada do oficial (Ed25519) e o
  servidor só aceita chave cadastrada em `assinatura_da_atualizacao`. Desde a
  3.7.1 a assinatura e o hash de cada arquivo são **reconferidos** ao aprovar
  e ao aplicar, e o aplicador recusa arquivo que não esteja no manifesto.
- **A chave privada não mora no servidor nem em pasta compartilhada ou
  sincronizada** (uma pasta «compartilhada comigo» de um Proton Drive, Google
  Drive ou OneDrive é compartilhada: quem tem a pasta assina um pacote que o
  servidor aceita). Pendrive guardado com o oficial, ou cofre de senhas; e a
  senha da chave só ele.
- Se a chave vazou ou passou por pasta compartilhada: gerar par novo
  (`tools\chave_de_atualizacao.py gerar`), cadastrar a pública no servidor
  **antes** e aposentar a antiga.
- Quem aplica confere o SHA-256 informado com o pacote (tela de
  Atualizações). Pacote sem origem conhecida não se aplica.

## 6. Backup

- A cópia diária é **o banco inteiro**: a pasta das cópias é só de quem
  precisa (§1.4), e o espelho numa nuvem vai **cifrado**. A cifra está
  desligada de fábrica e se liga em [`BACKUP.md`](BACKUP.md), seção 3 — com a
  chave guardada **fora da máquina**: chave perdida é backup ilegível, e é por
  isso que ligar a cifra é decisão da casa, e não do instalador.
- A rotina que faz o backup precisa **ler** a chave; confira que a conta dela
  consegue (§4).
- O teste de restauração é o processo **«Teste de restauração do backup»** da
  central de automação (`BACKUP_TESTE_RESTAURACAO`): restaura o pacote mais
  novo num banco **descartável**, confere as contagens contra o manifesto,
  apaga e registra. Ele nasce **desligado** — ligue-o em Automação, e confira
  que a conta do banco pode criar banco (CREATEDB). Ver `BACKUP.md`, seção 7.
  (Até 26/10/2026 este item dizia que «a própria rotina» já fazia isso; não
  havia teste de restauração nenhum no código.)

## 7. Usuários e papéis dentro do sistema

- **Cada pessoa tem a sua conta**, com o papel que exerce: ADMIN (o oficial),
  MANAGER (quem gere), USER (quem pratica ato), AUDITOR (quem **só vê** — desde
  a 3.7.1 o AUDITOR não grava em tela nenhuma).
- **Robôs e agentes** são usuários marcados como robô: só nascem USER ou
  AUDITOR, não entram nas telas de usuários, configurações, atualizações,
  caixa e selador, e nenhum selo sai em nome deles.
- **Caixa:** o estorno de lançamento de caixa **fechado** exige ADMIN ou
  MANAGER **e** a senha de outra pessoa com o mesmo papel, na hora; a
  conferência do caixa é só de ADMIN/MANAGER e nunca de quem o operou. Com
  uma só pessoa nesses papéis, o estorno de caixa fechado não sai — decida
  quem é o segundo antes de precisar.
- **Importação do acervo** (RCPN, Livro 3, padrão) aceita o perfil USER
  porque uma serventia decidiu assim; o acervo-fonte trocado por engano não
  tem volta. Se na sua casa isso é do oficial, peça a mudança — é uma linha
  por rota.
- **Rotinas que escrevem sem clique** (envio automático à CENSEC, correção
  automática do RTD/PJ) têm interruptor em **Configurações → Rotinas que
  escrevem sem clique**. Nascem ligadas; saiba que estão.
- **Segundo fator** no login, quando disponível na sua versão, para quem é
  ADMIN e MANAGER.
- A **lista de atenção para fraudes**, a trava do selo pago e a conferência
  diária (`compliance`) só protegem se alguém lê o que elas acusam: defina
  quem lê o despacho da conferência todo dia.

## 8. O que é de terceiros, na mesma máquina

Programas de centrais e de órgãos (sincronizadores do ONR, a máquina virtual
do selador, o sistema antigo que ficou como acervo) costumam vir com pastas e
compartilhamentos abertos e serviços rodando como SYSTEM a partir de
executáveis que qualquer usuário altera. **Não mexa neles por conta própria**
— quem responde por eles é quem os fornece —, mas **meça e comunique**: a
mesma lista do §9 serve, e o resultado vai para o fornecedor por escrito.

## 9. Lista de conferência mensal

| o quê | comando | o esperado |
|---|---|---|
| pasta de dados | `icacls C:\ProgramData\CartorioGestao` | SYSTEM e Administradores F; Usuários RX; sem conta de pessoa |
| segredos | `icacls C:\ProgramData\CartorioGestao\*.cred` | só SYSTEM e Administradores |
| Python do serviço | `type …\runtime\pyvenv.cfg` | `home` em `C:\Program Files` |
| compartilhamentos | `Get-SmbShare \| Get-SmbShareAccess` | nenhum «Todos» com controle total |
| Convidado | `net user Convidado` | «Conta ativa: Não» |
| papéis do banco | `SELECT rolname, rolsuper FROM pg_roles WHERE rolname NOT LIKE 'pg\_%'` | o papel do sistema **sem** superusuário; um reserva com |
| auditoria | `SELECT tgname FROM pg_trigger WHERE tgrelid='producao.audit_logs'::regclass` | `audit_logs_cadeia`, `audit_logs_imutavel`, `audit_logs_imutavel_truncate` |
| rotinas | `Get-ScheduledTask` (as do sistema) | pasta só de administradores; conta certa; nenhuma órfã |
| firewall | `Get-NetFirewallRule -DisplayName 'Cartorio Gestao*'` | perfis Privado/Domínio; sem regra genérica `python.exe` |
| conferência da casa | o despacho diário do `compliance` | `CAIXA_CADEIA` e `AUDITORIA_CADEIA` sem achado |

## 10. O que o sistema já faz sozinho (para não duplicar)

Ao subir, ele aplica a permissão dos segredos, acrescenta as colunas e o
gatilho da corrente da auditoria, instala as funções do banco, recusa caminho
de rede nas pastas configuradas, só aceita Chrome e LibreOffice configurados
dentro das pastas de programas, mascara CPF e CNPJ na auditoria, registra toda
exportação de planilha e isola o navegador que gera os PDFs da rede. O que
este guia pede é a outra metade — a que só quem administra a máquina pode
fazer.

# Backup — o que leva, como se protege e como se restaura

> Lote LX14 (19/10/2026), a partir dos achados A7 e A8 do LS03 e M5 do LS01.
> Quem gera o pacote é `backup.py`; a tela é **Administrativo → Configurações**.
>
> **A regra que não se negocia:** o backup é o caminho de volta. Nada do que
> está aqui impede de abrir um backup antigo — feito antes desta versão, sem
> cifra, ou com cifra.

## 1. O que o pacote leva

| Dentro do zip | O que é |
|---|---|
| `banco/cartorio_gestao.sqlite3` | o banco. **Desde a migração para o PostgreSQL, é um `pg_dump -Fc` do schema da casa**, e não um arquivo SQLite — o nome ficou o de sempre para a conferência e as ferramentas antigas acharem. Os backups de antes da migração trazem, nesse nome, o SQLite de verdade. |
| `banco/cartorio_gestao.sqlite3.sha256` e `manifesto.json` | o SHA-256 do banco e o inventário; a conferência compara os dois. Desde 26/10/2026 o manifesto também diz o formato do banco (`banco_formato`) e **quantas linhas cada tabela tinha no mesmo instantâneo do `pg_dump`** (`banco_contagens`) — é contra elas que o teste de restauração confere (seção 7) |
| `arquivos/…` | as digitalizações (só no **completo**) |
| `acervo/acervo_eoficio.sqlite3` | o acervo do E-Ofício (só no **completo**, e só se a opção abaixo não o tirar) |

O **diário** leva só o banco; o **completo** (semanal) leva também as
digitalizações e o acervo.

## 2. O que o pacote NÃO leva, de propósito

`secret.key`, `cofre.key`, `dois_fatores.key` e todos os `*.cred` ficam na
pasta de dados e **não vão no backup**: são os segredos da casa (a chave do
cookie de sessão, a chave do cofre, as senhas das Centrais, do selador, dos
robôs, do WhatsApp e da cifra do backup). Guarde uma cópia deles **à parte**,
em lugar seguro, para reinstalar o servidor.

**Desde o LX14 o banco também não leva mais segredo:** as chaves de API dos
robôs (`robo_config`) e os tokens do WhatsApp (`wa_config`) saíram das tabelas
e moram em `robos.cred` e `whatsapp.cred`, cifrados com a `cofre.key`. A linha
da tabela continua, vazia.

> **`cofre.key` e os `.cred` andam juntos.** Um `.cred` do cofre sem a
> `cofre.key` não abre — é para isso que ele é cifrado (copiado sozinho, não
> entrega nada). Perdeu a chave? As telas dizem «não configurado» e o
> segredo se digita de novo; nada no banco depende dela.

## 3. A cifra do pacote (opcional, desligada de fábrica)

**Onde:** Configurações → **Proteção do backup** → «Ligar a cifra» (só o
ADMIN). A senha tem no mínimo 12 caracteres e é gravada no cofre
(`backup.cred`) — **nunca no banco**, porque iria dentro do pacote que ela
fecha. A tela só diz se a cifra está ligada.

**Anote a senha fora do servidor.** Se o servidor se perder, o pacote cifrado
só abre com ela — e ninguém, nem quem fez o sistema, abre sem.

**Como fica o pacote:** o mesmo nome (`backup_banco_<data>.zip`,
`backup_completo_<data>.zip`), para a retenção e o espelho continuarem
achando-o; quem diz que ele é cifrado são os primeiros bytes
(`CG-BACKUP-CIFRADO`). Por dentro: AES-256-GCM em blocos de 1 MiB, com a chave
derivada da senha por scrypt; o número de cada bloco e a marca do último
entram na autenticação, de modo que pacote truncado ou adulterado é recusado,
e não aberto pela metade. O Windows Explorer não o abre como zip — é esperado.

**Antes de ganhar o nome**, o pacote cifrado é decifrado de novo e comparado
(SHA-256) com o zip que já tinha passado na conferência. Se não bater, fica
como `.cifrado.parcial` para exame e o nome definitivo não aparece.

**Desligar** volta os próximos pacotes ao zip comum; os que já saíram
cifrados continuam pedindo a senha de quando foram feitos (troque a senha só
sabendo disso, e guarde a antiga enquanto houver pacote dela na retenção).

**«A senha guardada não abre»** na tela quer dizer que a `cofre.key` sumiu:
os pacotes continuam saindo, **sem cifra** (backup que falta é pior), até
alguém gravar a senha de novo.

## 4. O acervo do E-Ofício fora do completo (opcional)

Na mesma seção: «Tirar o acervo do E-Ofício do backup completo». De fábrica
ele vai (é o comportamento de antes). Tire só se houver uma cópia dele
guardada à parte: ele não muda mais, e leva a senha do selador e o
`Secret_Code` do CNIB em texto claro (A7 do LS03).

## 5. Quem lê a pasta das cópias

`pasta_de_backups` pede, a cada processo, a ACL de **SYSTEM, Administradores
e a conta que roda o sistema** (Windows: `icacls … /inheritance:r /grant:r`;
fora dele, permissão 0700). Na subida, o mesmo vale para `secret.key`,
`*.key`, `*.cred` e `logs\servidor.log` (`permissao_local`).

- **Falhar é aviso**, no log `cartorio.permissoes`, e o backup sai assim
  mesmo — disco FAT/exFAT, pasta de rede, `icacls` ausente.
- **O espelho fora do servidor** (o `ESPELHAR_BACKUP.cmd`, que roda na sessão
  do usuário) precisa rodar **como administrador elevado** (ou como tarefa
  agendada com «executar com privilégios mais altos»): uma sessão comum, sem
  elevação, deixa de ler a pasta. Conferir no primeiro espelho depois desta
  versão.

## 6. Restaurar

**Passo 1 — o zip de sempre, a partir de qualquer pacote.** Com o servidor
parado, na pasta do sistema:

```
python backup.py abrir C:\CartorioGestao_Copias\backups\backup_banco_2026-10-19.zip C:\restaurar\pacote.zip
```

- Pacote **sem cifra** (antigo ou novo): é copiado e conferido.
- Pacote **cifrado**: a senha é perguntada (nunca na linha de comando, que fica
  no histórico do console); ou, na mesma máquina, `--pasta-de-dados
  C:\ProgramData\CartorioGestao` a lê do cofre.
- Em qualquer caso, a saída só aparece **depois** da conferência (zip
  íntegro, banco dentro, SHA-256 do manifesto). Senão, a mensagem diz o
  problema e nada fica com cara de bom.
- Só conferir, sem gravar: `python backup.py conferir <pacote>`.

**Passo 2 — descompactar** `pacote.zip` numa pasta de trabalho.

**Passo 3 — o banco.**
- Backup **depois da migração** (`banco/cartorio_gestao.sqlite3` é um
  `pg_dump -Fc`): `pg_restore` dele no banco da casa, com o serviço parado e o
  binário de `CG_PG_BIN` (por exemplo `pg_restore --clean --if-exists -d
  "<CG_PG_DSN>" banco\cartorio_gestao.sqlite3`). Ensaie antes numa cópia.
- **Num servidor NOVO (banco vazio), prepare o `public` antes.** O `pg_dump`
  leva só o schema da casa, e o schema usa coisas que moram no `public`: a
  collation `cg_nocase`, as extensões `pg_trgm` e `unaccent` e as funções de
  `banco_pg_funcoes.sql`. Sem elas o `pg_restore` para na primeira tabela
  (medido em 26/10/2026). O caminho ensaiado é o do teste de restauração:
  `banco_pg.preparar_banco_vazio(cursor)` com um cursor ligado ao banco vazio,
  e então `pg_restore --no-owner --no-privileges --exit-on-error -d <banco>`.
  É o que `backup_automacao.py --testar-restauracao` faz toda vez, num banco
  descartável.
- Backup **de antes da migração** (o arquivo é SQLite de verdade): ele entra
  pela mesma carga da migração para o PostgreSQL, e não pelo `pg_restore`.

**Passo 4 — as digitalizações e o acervo** voltam de `arquivos/` e `acervo/`
para a pasta de dados.

**Depois de subir:** um backup antigo traz de volta, nas colunas, as chaves dos
robôs e os tokens do WhatsApp de quando foi feito. A subida as tira de lá
sozinha (`init_robo_schema`, `init_wa_schema`): se o cofre já tem aquele
segredo, **fica o do cofre** (é o mais novo) e a coluna só é esvaziada; se não
tem, o da coluna vai para o cofre. Nada impede a restauração, e a chave nova
não é trocada pela velha.

## 7. O backup no horário e o teste de restauração (26/10/2026)

Provimento CN/CNJ 213/2026, art. 12, § 3º, I (a cópia na periodicidade da
classe) e § 10 (o alerta ao responsável quando ela falha).

**Até esta versão o backup automático só saía no primeiro acesso ao sistema** —
e, pior, uma vez por *processo* do servidor: com o servidor de pé três dias, só
o primeiro dia tinha backup. A falha virava só uma linha `AUTO_BACKUP_FAILURE`
na auditoria. Agora são dois processos da **central de automação** (Automação →
processos), que **nascem desligados** — quem liga é o oficial:

| Processo | Agenda de fábrica | O que faz |
|---|---|---|
| `BACKUP_DIARIO` — «Backup do banco no horário» | todo dia, **18:00** (decisão do oficial, 26/10/2026) | o pacote do banco do dia, o completo quando devido (uma vez por semana, no dia de Configurações; o completo perdido sai no dia seguinte) e a retenção de 5 dias (seção 7.1). Não depende de alguém abrir o sistema |
| `BACKUP_TESTE_RESTAURACAO` — «Teste de restauração do backup» | domingo, 04:00 | restaura o pacote mais novo num banco **descartável**, confere as contagens, apaga o banco descartável e registra a rodada em `bk_restauracoes` |

- **O alerta é o da automação:** terminou em AVISO ou ERRO, aparece no painel,
  vira tarefa do responsável e vai por e-mail (se configurado em Automação →
  Configuração), e é lembrado enquanto seguir. Não há outro canal.
- **O primeiro acesso do dia continua como reserva** (a opção «backup
  automático» de Configurações governa só ele) e chama a mesma rodada: o pacote
  que a automação já gerou hoje não se repete, e uma trava na pasta dos backups
  (`backup_rodada.trava`) impede os dois ao mesmo tempo.
- **O teste nunca restaura por cima do banco da casa.** Ele cria um banco novo
  `cg_restauro_<data e hora>_<sorteio>`, restaura nele e o apaga; só aceita
  criar e apagar banco com esse formato de nome. O banco nasce no mesmo servidor
  do banco da casa, salvo se `CG_PG_DSN_RESTAURACAO` apontar outro (por exemplo,
  o servidor de teste). **A conta do banco precisa do privilégio CREATEDB**, e o
  servidor precisa de espaço para uma cópia do banco enquanto o teste roda.
- **E a conta NÃO pode ser superusuário** (revisão de segurança de 26/10/2026).
  O `pg_restore` executa o que o pacote traz com o papel da conexão; o banco
  descartável isola os dados, não os privilégios. O teste recusa (ERRO, nada
  restaurado) papel superusuário, membro de superusuário ou de
  `pg_execute_server_program`/`pg_write_server_files`/`pg_read_server_files`,
  ou com CREATEROLE, REPLICATION ou BYPASSRLS. **A conta `cg` da instalação é
  superusuário** — então, para o teste rodar, crie um papel só para ele e
  aponte `CG_PG_DSN_RESTAURACAO` para ele (sem a senha no DSN: ela vai no
  `pgpass` da conta do serviço, como a do `cg`):

  ```sql
  CREATE ROLE cg_restauro LOGIN CREATEDB PASSWORD '<senha forte>';
  ```

  `CG_PG_DSN_RESTAURACAO=host=127.0.0.1 port=<porta> user=cg_restauro dbname=postgres`
- **Só se restaura pacote que o sistema gerou.** A rodada do backup grava o
  nome e o SHA-256 de cada pacote em `bk_pacotes` (e na auditoria
  `AUTO_BACKUP_*`); o teste recusa o pacote que não está lá — inclusive pela
  linha de comando. Pacote gerado antes de 26/10/2026 é recusado até o próximo
  backup sair.
- **O pacote é aberto na pasta de dados do servidor** (`restauracao_tmp`,
  restrita), e não na pasta dos backups: o pacote decifrado e o dump em claro
  nunca ficam na pasta que sai da serventia. Ela precisa de espaço para uma
  cópia do pacote e do dump enquanto o teste roda.
- **O que ele confere:** cada tabela que voltou, contra a contagem que o
  manifesto gravou no mesmo instantâneo do `pg_dump`; e que as tabelas
  principais (usuários, configurações, auditoria, anexos, protocolo, caixa,
  selos, matrículas e atos do RI, assentos do RCPN, atos de Notas, títulos do
  Protesto) voltaram. Pacote de antes desta versão (sem contagens) restaura e
  sai como AVISO, por não ter contra o que conferir.
- **Para a correição:** cada rodada fica em `bk_restauracoes` (data, pacote,
  SHA-256 do pacote, tipo, contagens, divergências, tempo). Pela linha de
  comando, na pasta do sistema e com as variáveis do servidor:
  `python backup_automacao.py --testar-restauracao` (roda agora) e
  `python backup_automacao.py --historico` (as últimas 20).

### 7.1 A retenção: 5 dias, e o completo-base fica (decisão do oficial, 26/10/2026)

«Salva os últimos 5 dias, apaga os mais antigos» e «completo uma vez por
semana». O diário traz o banco inteiro, mas **as digitalizações e o acervo só
existem no completo** — por isso, a cada rodada (`backup_rotina.aplicar_retencao`):

- **ficam** todos os pacotes dos últimos 5 dias (hoje inclusive);
- **ficam** o pacote mais novo e o **completo-base** dele (o completo mais
  recente com data igual ou anterior), **mesmo com mais de 5 dias** — sem ele,
  o mais novo não devolve a casa inteira. Se o backup parar de sair, a pasta não
  se esvazia: o último pacote e a base dele continuam lá;
- **sai** o resto.

O que ela apaga, e o que nunca:

- só arquivo com o nome que a rodada dá — `backup_banco_AAAA-MM-DD.zip` e
  `backup_completo_AAAA-MM-DD.zip` —, direto na pasta dos backups (nem
  subpasta, nem atalho). Backup manual, o completo de outra rotina
  (`backup_completo_AAAAMMDD_HHMMSS.zip`), o formato antigo
  `backup_automatico_*.zip` e os `.parcial` não são tocados;
- a data é a do **nome**, e não a da gravação (uma cópia muda a gravação);
- pacote com data a partir de 26/10/2026 só sai se estiver em `bk_pacotes`; o
  que não está fica, e vira aviso na automação para alguém conferir;
- **o espelho fora do servidor e o Proton não são tocados**: a retenção só
  conhece a pasta dos backups;
- cada rodada que apagou alguma coisa grava `AUTO_BACKUP_RETENCAO` na
  auditoria, com a lista, o completo-base que ficou fora da janela, o
  **agente** (o processo da automação ou a reserva do primeiro acesso) e **a
  mando de quem** (a retenção decidida pelo oficial).

O número de dias é **Configurações → Retenção dos backups automáticos (dias)**
(`backup_retencao_dias`, 5 de fábrica, mínimo 3). As chaves antigas
(`backup_retention`, 30 pacotes; `backup_completo_retencao`, 8 completos)
contavam arquivos por tipo e não governam mais nada.

## 8. A cópia imutável fora da casa — AINDA NÃO

O espelho fora do servidor, imutável, é exigência do mesmo provimento, e **o
oficial ainda vai escolher o armazenamento** (26/10/2026). Nada foi construído
para ela, e nenhum serviço foi escolhido. O lugar onde ela entra está marcado
em `backup_rotina.rodada` («A CÓPIA IMUTÁVEL FORA DA CASA»): depois de o pacote
passar na conferência, e só do pacote conferido; a falha dela vira item de
`falhas`, e a automação avisa como avisa a falha do pacote.

## 9. A regra do gestor e o completo semanal — decidido em 26/10/2026

Até esta versão a conferência diária do gestor
(`gestor_conferencia.regra_backup`) acusava **CRÍTICO** quando o último
`backup_completo_*.zip` tinha mais de **1 dia** — e o completo que o sistema
gera é semanal: com só o sistema gerando backup, a regra acusaria seis dias em
sete. **O oficial decidiu: «completo uma vez por semana».** A regra passou a
fazer duas cobranças:

| Achado | Quando | Limite |
|---|---|---|
| `BACKUP:completo` | o último completo tem mais de **7 dias** (`BACKUP_COMPLETO_DIAS_TOLERADOS`) | uma vez por semana |
| `BACKUP:diario` | o pacote mais novo — diário do banco **ou** completo, que também leva o banco — tem mais de **1 dia** (`BACKUP_DIAS_TOLERADOS`) | o do dia |

A folga de um dia no diário é porque a conferência roda de manhã (07h30) e o
backup no horário sai às 18h: de manhã, o «do dia» é o da noite anterior. Sem
backup nenhum na pasta, sai um achado só («Nenhum backup encontrado»).

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
| `banco/cartorio_gestao.sqlite3.sha256` e `manifesto.json` | o SHA-256 do banco e o inventário; a conferência compara os dois |
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

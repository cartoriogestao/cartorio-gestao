# O servidor reserva no macOS

> Pedido do oficial em 07/11/2026: «um servidor extra num macOS, como backup do servidor
> original, em uma porta diferente, mas com banco de dados sincronizado». Decidido com ele:
>
> - a reserva **só lê** enquanto o principal está no ar, e **assume** se ele cair;
> - a pasta de arquivos (papéis digitalizados, PDFs, imagens) também vai para o Mac.

## Como funciona

| peça | no principal (Windows) | na reserva (macOS) |
|---|---|---|
| banco | PostgreSQL 18, porta 5434, schema `producao` | PostgreSQL 18 próprio, porta 5434, o mesmo schema |
| como o banco chega | publicação `cg_reserva` | assinatura `cg_reserva` (réplica **lógica**, segundos de atraso) |
| o sistema | porta 8765, descoberta na 8766 | porta **8775**, sem descoberta, faixa «SERVIDOR RESERVA» |
| quem grava | o sistema, como sempre | **ninguém**: o sistema entra no banco com `cg_leitor`, que só tem SELECT |
| arquivos | a pasta da casa (`archive_root`) e as pastas configuradas fora dela | cópia de 5 em 5 minutos, sem apagar nada (`sincronizar.sh`) |
| segredos | `secret.key`, `cofre.key`, `*.cred` na pasta de dados | pacote cifrado **para a chave do Mac**, que chega pela réplica |

**Por que só lê.** Protocolo, selo, folha e ato saem de sequências do banco. Com os dois servidores
lançando, o mesmo número sairia duas vezes, um em cada lado, e isso não tem conserto no livro.

**Por que réplica lógica.** A física copia o disco do banco e exige o mesmo sistema operacional e o
mesmo idioma do banco. Windows e macOS não têm nem um nem outro em comum. A lógica manda linhas.

**O que a réplica lógica não leva, e quem leva:**

- **Esquema.** Uma versão nova pode criar tabela ou coluna. A sincronia roda o `reserva.py esquema`
  de 5 em 5 minutos. Sem isso, a réplica para na primeira linha que usa a coluna nova (ensaiado).
- **Sequências.** O `assumir` acerta o próximo número de cada tabela pelo maior que já existe.

**O que a reserva mostra.** Medido na casa de ensaio, com o perfil ADMIN: das 893 telas, 848 abrem.
As outras gravam algum rastro ao abrir e mostram «abra-a no servidor principal», em vez do erro 500.
Formulário nenhum entra, salvo o de entrar e o de sair. Enquanto é reserva, as telas que abrem
documento das pastas configuradas fora da pasta de arquivos procuram o caminho do Windows e não
acham. Depois do `assumir`, elas apontam para as cópias do Mac. O login na reserva não fica na tabela de
auditoria (o banco não grava), só no log do servidor.

## Os segredos da pasta de dados

A réplica leva o banco, e a sincronia leva os arquivos. Faltavam os segredos da pasta de dados do
principal:

- `secret.key`, que assina as sessões e os códigos dos links impressos;
- `cofre.key` e os `*.cred`, com as senhas das integrações e a chave dos códigos de acompanhamento
  que vão para os clientes.

Sem eles, a reserva que assume perde as integrações, e os códigos entregues deixam de abrir.

Eles vão **cifrados de uma instalação para a outra** (`reserva_chaves.py`):

1. Na instalação, o Mac sorteia um par de chaves. A **privada** nunca sai dele
   (`reserva-chave.privada`, só o dono lê). A **pública** vai ao principal no SQL do passo A2.
2. O principal, de 5 em 5 minutos, cifra os segredos para essa pública e grava o pacote na tabela
   `reserva_pacote`, só quando algum mudou.
3. A réplica leva a tabela ao Mac, pela conexão SSL. A sincronia abre o pacote com a privada e
   grava os arquivos na pasta de dados do Mac.

Só a privada do Mac abre o pacote. Nem o próprio principal o abre depois de cifrado. Quem copiar o
banco, um backup ou o tráfego leva bytes que não abrem. Ficam de fora o `pgpass.conf` do Windows (o
Mac tem o seu) e o certificado `.pfx`.

## A ordem

1. **B1**, no Mac: instalar. É o que sorteia a chave da reserva.
2. **Parte A**, no Windows: o SQL (que já leva a pública do Mac), o SSL, o acesso e o reinício.
3. **B2 a B4**, no Mac.

## Parte A — o lado do Windows (uma vez)

> **Decidido pelo oficial em 07/11/2026: a porta 5434 abre só para o IP do Mac.**
> `docs/SEGURANCA_REDE.md` fixou que o banco do principal não escuta a rede. A reserva é a
> única exceção, e estreita:
>
> - uma linha `hostssl` no `pg_hba`, só para o usuário `cg_replica`, só do IP do Mac, com SCRAM;
> - o firewall libera a 5434 só para esse IP;
> - o tráfego vai cifrado (SSL), e o `cg_replica` não grava nada.
>
> O túnel SSH, a outra opção, ficou de fora: pedia ligar o servidor SSH do Windows.

**A1.** No Mac, **depois do B1**, gere o SQL do principal e leve-o ao Windows. Ele leva a chave
pública da reserva (a privada não sai do Mac):

```
cd ~/Library/Application\ Support/CartorioGestao
(set -a; source reserva.env; venv/bin/python sistema/tools/reserva.py sql-do-principal) > principal.sql
```

**A2.** No Windows, rode o SQL. A senha do `cg_replica` é nova: anote-a, porque ela vai para o
`~/.pgpass` do Mac.

```
psql -h 127.0.0.1 -p 5434 -U cg -d cartorio -v senha=<senha nova> -f principal.sql
```

O que o SQL faz (pode rodar de novo sem estragar nada):

- liga `wal_level = logical`, que só vale depois de reiniciar o serviço;
- põe o **teto de 20 GB** no log guardado para a reserva, para um Mac desligado não encher o disco do
  principal;
- cria o usuário `cg_replica`, que entra, replica e lê, mais nada;
- dá identidade de réplica a tabela sem chave, se houver alguma (a casa tinha 0 em 07/11/2026);
- cria a publicação;
- grava a chave **pública** da reserva em Configurações. A partir do reinício do sistema, o
  principal publica o pacote de segredos cifrado para ela.

A conferência no fim mostra `REINICIE O SERVIÇO` enquanto o `wal_level` não valer.

**A3.** No `pg_hba.conf` do Windows (guarde uma cópia antes), acrescente uma linha só para o IP do Mac:

```
hostssl cartorio cg_replica <IP do Mac>/32 scram-sha-256
```

Ponha também `listen_addresses = 'localhost,<IP do Windows>'` e libere a porta 5434 no firewall
**só para o IP do Mac**.

O `hostssl` exige `ssl = on` no `postgresql.conf`, com um certificado (`server.crt` e `server.key`).
Sem SSL, a réplica levaria pela rede, em texto aberto, todos os dados da casa. Se o PostgreSQL do
Windows ainda não tem SSL, este é o passo que ele pede.

**A4.** Numa janela sem movimento, reinicie o serviço do PostgreSQL. É coisa de segundos.

## Parte B — o Mac

**B1. Antes de instalar:**

- conta própria para o servidor, com **login automático** (os serviços são LaunchAgents e sobem com
  a sessão);
- em Ajustes do Sistema › Bateria/Energia, **nunca dormir**;
- IP fixo na rede;
- a pasta do código **fora** de Documentos, Mesa e Downloads. O macOS impede os serviços de abrir
  arquivos nessas pastas (medido no ensaio: `file system sandbox blocked open()`).

```
brew install postgresql@18 python@3.12
bash installer/macos/instalar_reserva.sh
```

O instalador:

- copia o código para `~/Library/Application Support/CartorioGestao/sistema` e monta o venv;
- cria um PostgreSQL só da reserva (porta 5434, com senha, idioma pt-BR pelo ICU);
- cria os usuários `cg` e `cg_leitor`, com as senhas no `~/.pgpass`;
- sorteia a chave da reserva (`reserva-chave.privada`), uma vez só;
- instala três serviços do launchd: `br.com.cartoriogestao.postgres`, `.servidor` e `.sincronia`.

Pode rodar de novo, e é assim que se atualiza o código.

**B2.** Em `~/Library/Application Support/CartorioGestao/reserva.env`, ponha o IP do Windows em
`CG_RESERVA_PRINCIPAL_DSN`. O `sslmode=require` já vem no exemplo. No `~/.pgpass`, acrescente:

```
<IP do Windows>:5434:cartorio:cg_replica:<a senha do A2>
```

**B3.** Os arquivos (recomendado). A cópia vai **direto do Windows para o Mac**, pela rede da
casa, por compartilhamento do Windows (SMB). Nenhum serviço de fora entra no caminho.

- compartilhe no Windows a pasta da casa, só leitura, para um usuário só da reserva;
- **ligue a criptografia do compartilhamento**, porque sem ela os documentos passam abertos pela
  rede. No PowerShell do Windows, como administrador:
  `Set-SmbShare -Name arquivos -EncryptData $true`. O macOS fala SMB 3 cifrado sozinho;
- ponha `CG_RESERVA_SMB=//usuario@<IP do Windows>/arquivos` no `reserva.env`;
- monte-a uma vez pelo Finder (Ir › Conectar ao Servidor) marcando «lembrar a senha». A senha fica
  nas Chaves, e a sincronia monta sozinha dali em diante.

**As pastas configuradas fora da pasta de arquivos** (Configurações: documentos das matrículas,
firmas e exportação de Notas, gratuidade, pastas de importação): a sincronia lê no banco onde cada
uma está e anota no `sincronia.log` as que ficam fora da pasta de arquivos e não têm
compartilhamento: `pastas: FALTA COMPARTILHAR D:\Matriculas (ri_pasta_matriculas_doc)`. Para
cada uma:

- compartilhe-a no Windows do mesmo jeito: só leitura, mesmo usuário, `-EncryptData $true`;
- acrescente-a em `CG_RESERVA_SMB_PASTAS`, no `reserva.env`:
  `D:\Matriculas=//cartorio@<IP do Windows>/matriculas`, várias separadas por `;`;
- monte-a uma vez pelo Finder, como a primeira.

As cópias ficam em `pastas/` na instalação (`D:\Matriculas` → `pastas/D_Matriculas`), também
sem apagar nada. A pasta de backup fica de fora de propósito: o banco já chega pela réplica.

**Como a cópia anda.** De 5 em 5 minutos, o `rsync` compara cada arquivo dos dois lados pelo
tamanho e pela data, e só passa pela rede o que é novo ou mudou. Um arquivo interrompido no meio
continua na volta seguinte. O que sumir do Windows continua no Mac. A primeira volta traz o acervo
inteiro e é a demorada; as seguintes levam segundos. A defasagem é de até 5 minutos, contra
segundos do banco.

**B4.** Monte a réplica:

```
cd ~/Library/Application\ Support/CartorioGestao
set -a; source reserva.env; set +a
venv/bin/python sistema/tools/reserva.py montar
venv/bin/python sistema/tools/reserva.py situacao      # repita até «EM DIA»
venv/bin/python sistema/tools/reserva.py conferir      # contagem de cada tabela nos dois lados
```

O servidor da reserva sobe sozinho quando o esquema chega. Até lá, o launchd o religa e o log diz o
que falta. Abra `http://<IP do Mac>:8775`: a faixa vermelha diz «SERVIDOR RESERVA».

## O dia a dia

- **`sincronia.log`** (na pasta da instalação): a cada 5 minutos, as pastas, as chaves
  (`chaves: em dia` ou `chaves: N arquivo(s) recebidos`) e uma linha terminando em `EM DIA` ou
  `ATRASADA`. Atrasada por mais de uma hora, veja o log do PostgreSQL da reserva
  (`logs/postgres.log`).
- **Versão nova:** atualize primeiro o principal, como sempre. O esquema chega à reserva sozinho em
  até 5 minutos. Depois atualize o código do Mac (`git pull` e `instalar_reserva.sh`). O contrário,
  código novo num esquema velho, pode quebrar telas da reserva.
- **Reserva desligada por dias:** passados os 20 GB, o principal descarta o log, e a réplica não
  retoma sozinha. Remonte com `reserva.py montar --refazer` (minutos).

## Assumir — o principal caiu

1. **Garanta que o Windows não volta a lançar:** desligue a máquina, ou pare o serviço do Cartório
   Gestão nela. Se os dois lançarem, o mesmo número sai duas vezes.
2. No Mac:

   ```
   bash ~/Library/Application\ Support/CartorioGestao/sistema/installer/macos/assumir.sh ASSUMIR
   ```

   O script:
   - desliga a réplica;
   - acerta as sequências (no ensaio: 286 numa base de 331 tabelas, em menos de um segundo);
   - aponta a pasta de arquivos e as outras pastas configuradas para as cópias do Mac;
   - troca o `reserva.env` para o modo principal;
   - reinicia o servidor. Ele sobe na porta do principal (8765) e responde à descoberta, e os balcões
     o acham sozinhos.

**O que o Mac ainda não faz como principal** (o inventário está em `docs/MIGRAR_PARA_MACOS.md`):

- assinatura com o token A3;
- os robôs e as tarefas do Agendador do Windows;
- os caminhos `C:\` gravados em outras configurações;
- os programas das Centrais que só existem para Windows.

O balcão lança. O que depende dessas peças espera o principal voltar ou a migração delas.

## A volta do principal

Depois de um `assumir`, **o Mac passou a ser o principal**, e o banco do Windows ficou para trás.
Não ligue o serviço do Cartório Gestão no Windows. Para devolver o papel ao Windows:

1. numa janela sem movimento, pare o servidor do Mac (`launchctl bootout gui/$(id -u)/br.com.cartoriogestao.servidor`);
2. copie o banco do Mac para o Windows (`pg_dump` do schema `producao` no Mac e `pg_restore` no
   Windows: `docs/BACKUP.md`) e confira as contagens;
3. no Windows, apague o slot velho, que continuaria segurando log:
   `SELECT pg_drop_replication_slot('cg_reserva');`
4. ligue o Windows e reinstale a reserva no Mac:
   - `reserva.env` de volta ao modo reserva (há uma cópia em `reserva.env.antes-de-assumir`);
   - `reserva.py montar --refazer`;
   - `launchctl kickstart -k gui/$(id -u)/br.com.cartoriogestao.servidor`.

## O ensaio de 07/11/2026

Dois PostgreSQL 18 neste Mac de desenvolvimento, um como principal e outro como reserva. O principal
tinha o esquema verdadeiro, criado pelo próprio sistema (330 tabelas). O que se conferiu:

- `sql-do-principal` aplicado duas vezes, sem erro na segunda;
- `montar`: 330 de 330 tabelas em dia, contagens iguais;
- um lançamento no principal chegou em menos de 2 segundos;
- versão nova (uma coluna e uma tabela, com linhas): a réplica parou e o `situacao` disse
  `ATRASADA`. O `esquema --aplicar` resolveu, e as linhas paradas chegaram;
- o `app.py` de verdade, como reserva: login de um usuário que veio pela réplica, telas, formulário
  recusado (503), nada na porta 8766;
- o instalador num HOME isolado, com os serviços pelo launchd: o servidor ficou no ar e a sincronia
  gravou o log. O serviço do PostgreSQL não foi ensaiado assim: o binário do ensaio estava em
  Documentos, e o macOS barrou;
- `assumir.sh` com o principal desligado: sequências acertadas, servidor de volta na 8765 sem a
  faixa, cadastro novo com o id seguinte, pasta de arquivos apontada para o Mac.

Depois do ensaio, entraram os segredos e as pastas configuradas. Esses dois foram testados contra o
banco de teste, com uma pasta local no lugar do compartilhamento: o principal publica, a reserva
abre e grava, e o `pastas --apontar` troca a configuração. O SMB de verdade e o pacote atravessando
a réplica entre duas máquinas ficam para a implantação.

Os testes automáticos são `tests/test_modo_reserva.py` (o sistema com o usuário só de leitura,
inclusive a subida inteira) e `tests/test_ferramenta_reserva.py`.

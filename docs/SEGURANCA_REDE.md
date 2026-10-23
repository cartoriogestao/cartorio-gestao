# Segurança de rede e da implantação — recomendações

> Documento de implantação: o que se configura no servidor, e não no código.
> Cada seção diz de que achado veio. Este documento trata do **banco**, do
> **HTTPS** e do **`/saude`**; as permissões de pasta, o Python do serviço, as
> rotinas, a chave da atualização, o backup e os papéis estão no guia
> [`SEGURANCA_IMPLANTACAO.md`](SEGURANCA_IMPLANTACAO.md), que é o lugar por
> onde se começa.

## O PostgreSQL da casa (A9 do LS03, LX14 — 19/10/2026)

**Como as primeiras instalações ficaram.** A entrega do PostgreSQL portátil
punha no `iniciar_servidor_servico.cmd` um `CG_PG_DSN=host=127.0.0.1 port=5434
user=cg dbname=cartorio` **sem senha**, com o `pg_hba.conf` aceitando o usuário
`cg` em `trust` a partir de 127.0.0.1. **Conferido em 22/10/2026 numa
instalação em produção: o `pg_hba` já exige senha (SCRAM) e a senha mora num
`pgpass.conf` protegido** — o que segue é o roteiro para quem ainda estiver em
`trust`, e a conferência do item 4 diz em qual caso a sua instalação está. O
que continuava aberto naquela instalação era o `cg` ser **superusuário**; o
roteiro para tirar isso está no guia, seção 2.2.

**O risco.** `trust` em 127.0.0.1 quer dizer: **qualquer conta ou processo do
próprio servidor** entra no banco inteiro como `cg`, sem senha — inclusive uma
conta de usuário comum logada na máquina, ou um programa que alguém rodou
nela. Não é preciso estar na rede da casa: basta estar no servidor. E o `cg`
do PostgreSQL portátil é dono do cluster (no banco de teste ele é
superusuário, medido no LS03).

**A recomendação** (na ordem em que se faz, com o serviço parado):

1. **Dar senha ao `cg`, guardada como SCRAM.** No `psql` do
   `CG_PG_BIN`, ainda em `trust`:
   `SET password_encryption = 'scram-sha-256';` e
   `ALTER ROLE cg PASSWORD '<senha longa, só para o banco>';`
2. **Trocar `trust` por `scram-sha-256`** nas linhas de 127.0.0.1/32 e
   ::1/128 do `pg_hba.conf`, e recarregar (`pg_ctl reload`). Nenhuma linha
   para fora de 127.0.0.1: o banco não escuta a rede (`listen_addresses =
   'localhost'`), e a porta 5434 fica fechada no firewall.
3. **A senha vai num `pgpass`, e NÃO no `CG_PG_DSN`.** O sistema passa o
   `CG_PG_DSN` inteiro ao `pg_dump` do backup (`-d <dsn>`, em
   `banco_pg.copiar_para_arquivo`): uma senha dentro dele apareceria na linha
   de comando do processo, que outras contas da máquina enxergam. O
   `libpq` (do `psycopg` e do `pg_dump`) lê a senha sozinho do arquivo
   apontado por `PGPASSFILE`:
   - criar `C:\ProgramData\CartorioGestao\pgpass.conf` com a linha
     `127.0.0.1:5434:cartorio:cg:<senha>`;
   - pôr `set "PGPASSFILE=C:\ProgramData\CartorioGestao\pgpass.conf"` no
     `iniciar_servidor_servico.cmd`, ao lado do `CG_PG_DSN` (que continua sem
     senha);
   - a subida do sistema aplica a ele a mesma ACL dos outros segredos
     (`permissao_local.SEGREDOS_DA_PASTA`): SYSTEM, Administradores e a conta
     do serviço. Até a primeira subida, ou se o aviso de permissão aparecer no
     log, à mão: `icacls C:\ProgramData\CartorioGestao\pgpass.conf
     /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F`.
4. **Conferir:** `psql -h 127.0.0.1 -p 5434 -U cg cartorio` numa sessão
   comum, sem o `PGPASSFILE`, tem de pedir senha e recusar sem ela; o
   servidor do sistema tem de subir e o backup do dia tem de sair.

**O que muda para quem mexe no banco à mão:** as ferramentas (`psql`,
`pg_dump`, `pg_restore` da restauração — ver `docs/BACKUP.md`) passam a
precisar do mesmo `PGPASSFILE`, ou da senha digitada.

**O passo seguinte, e é decisão da casa:** tirar do `cg` o papel de
superusuário (um papel dono só do banco `cartorio`). Com superusuário, o
`pg_stat_activity` mostra o comando de todas as conexões e o `pg_shadow` a
senha SCRAM — o agente de IA já recusa os dois (LS03, LX14), mas o papel é a
defesa de verdade. O roteiro — **primeiro** um superusuário reserva, **depois**
o `NOSUPERUSER`, e nunca ao contrário — está em
[`SEGURANCA_IMPLANTACAO.md`](SEGURANCA_IMPLANTACAO.md), seção 2.2; a
imutabilidade da tabela de auditoria, na seção 2.3.

## O balcão na rede: HTTPS e o /saude (M7 e B6 do LS01, LX11 — 19/10/2026)

Os dois achados ficam **fora do código** de propósito: o que resolve é
configuração do servidor, e esta seção diz o que configurar e por quê.

### M7 — HTTPS na rede local

**O problema.** O sistema atende em `http://<servidor>:8765`. Sem TLS, a senha
digitada no login e o cookie de sessão viajam em claro pela rede da casa:
qualquer máquina na mesma rede (ou um aparelho plugado no switch, ou o Wi-Fi
de visitantes ligado na mesma rede) consegue lê-los e entrar como o usuário.
A espera depois de errar a senha (A4) e a troca de senha (M4) não protegem
contra isso: quem escuta a rede leva a senha **certa**.

**Por que não está no código.** HTTPS exige um certificado que os navegadores
do balcão aceitem, e isso depende da rede de cada serventia (nome do servidor,
domínio do Windows, quem administra as máquinas). Ligar HTTPS dentro do
programa sem o certificado instalado nos clientes faria o navegador recusar a
conexão — o balcão inteiro parado.

**O que o servidor deve configurar.**

1. **Um certificado interno** para o nome do servidor (ex.: `servidor-cartorio`
   ou o IP fixo), emitido pela autoridade certificadora do domínio — ou, sem
   domínio, um certificado próprio cuja raiz é instalada em
   «Autoridades de Certificação Raiz Confiáveis» de cada computador do balcão.
2. **Um proxy na frente do waitress**, na mesma máquina: IIS com ARR, Caddy
   ou nginx atendendo `https://<servidor>` (porta 443) e repassando para
   `http://127.0.0.1:8765`. Em **Configurações → Host do servidor**, troque
   para `127.0.0.1`, para a porta 8765 não ficar aberta para a rede sem TLS, e
   feche a regra da porta 8765 no Firewall do Windows (fica só a 443).
3. **Só depois de o HTTPS funcionar em todos os computadores**, ligar
   `SESSION_COOKIE_SECURE=True` (o cookie de sessão deixa de ir por HTTP).
   Ligado antes, ninguém consegue entrar: o navegador não manda o cookie por
   `http://`.
4. O proxy pode acrescentar `Strict-Transport-Security`; os outros cabeçalhos
   (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, a CSP em
   modo relatório) o próprio sistema já manda desde o LX11 (B1).

Enquanto o HTTPS não vem, o que reduz o risco: rede do balcão separada da rede
de visitantes, switch sem portas livres em área de público, e senhas trocadas
por cada usuário na tela **«minha senha»** (M4).

### B6 — o `/saude` responde sem login

**O que ele diz.** Nome do produto, versão, nome da serventia e o hostname do
servidor — e nada de acervo, usuário ou configuração.

**Por que fica aberto.** Quem chama o `/saude` não tem sessão:

- o **localizador** dos computadores do balcão, que procura o servidor na
  rede e confere que quem respondeu é mesmo o Cartório Gestão (e em que versão);
- o **atualizador**, que depois de aplicar a versão nova testa o `/saude` e
  **volta sozinho** à anterior se o servidor não responder;
- a conferência de produção (`compliance.py`) e o `INICIAR_SANDBOX.cmd --conferir`.

Pôr login no `/saude` quebraria os quatro, e o que ele entrega é o mesmo que a
descoberta automática (UDP 8766) já anuncia na rede. Com o proxy do M7, o
`/saude` passa a responder só por HTTPS, como o resto.

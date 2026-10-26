# Portal do cliente — instalação

> Decisão do oficial, 26/10/2026: «portal do cliente para acompanhar o pedido e
> baixar o recibo», no mesmo VPS do WhatsApp, com «código no recibo».

O cliente digita o **número do protocolo** e o **código de acompanhamento**
(os dois saem no recibo e no protocolo de recepção) e vê a situação do pedido;
quando houver, baixa o recibo em PDF.

## Como as peças se falam

```
  Servidor da serventia (Windows, SEM porta aberta para a internet)
     portal_cliente.py  — a cada 15 min (Agendador) ou no botão «Enviar agora»
        |
        |  HTTPS de SAÍDA, POST /portal/api/retratos, Authorization: Bearer <token>
        v
  VPS (Linux)  Apache :443 (Let's Encrypt)  →  127.0.0.1:8781  portal_vps.py
        ^                                        SQLite em /var/lib/cartorio-portal
        |  HTTPS, a página pública /portal/
  Cliente (celular, navegador)
```

- A VPS **nunca** alcança o servidor da serventia: é o desenho da caixa-postal
  do WhatsApp (`wa_puxar.py`) pelo outro lado.
- O que sobe é o **retrato mínimo**: número, *hash* do código (nunca o código),
  situação em linguagem simples, previsão, última movimentação, atribuição. O
  **Protesto** não sobe nada.
- **O recibo em PDF não sobe de fábrica** (correção de segurança de
  26/10/2026): ele leva o nome do pagador, os atos pedidos e os valores. Só
  sobe o da atribuição que o oficial liberar (`RECIBO_LIBERADO_NO_PORTAL`, em
  `portal_cliente.py`, vazia), e o do **Registro Civil** não sobe nem liberado.
  Enquanto nada for liberado, a página do portal mostra só a situação.
- A lista de campos é **fechada nas duas pontas**: o portal recusa o lote
  inteiro se vier um campo que ele não guarda.
- O protocolo encerrado sai do portal 90 dias depois; o aberto, um ano depois
  da abertura; e o portal apaga sozinho o que ficou 180 dias sem notícia.

**Banco: SQLite local, e não o MySQL que já existe na VPS.** São alguns
milhares de linhas e uma escrita a cada quinze minutos; o SQLite vem com o
Python e não pede driver, usuário de banco nem senha a mais. E isola o portal:
num MySQL compartilhado, outro programa da VPS (ou um erro de permissão dele)
leria os recibos dos clientes.

## Na VPS — passo a passo (como root, pelo SSH)

Nada de IP, nome de host, usuário ou senha da VPS neste repositório: são da
instalação. Nos comandos abaixo, `portal.exemplo.invalid` é o nome do site que
já atende o WhatsApp com HTTPS.

**1. Usuário próprio, sem login e sem senha** — o serviço não roda como root.

```sh
adduser --system --group --no-create-home --home /nonexistent cartorio-portal
install -d -o root -g root -m 755 /opt/cartorio-portal
install -d -o cartorio-portal -g cartorio-portal -m 700 /var/lib/cartorio-portal
install -d -o root -g cartorio-portal -m 750 /etc/cartorio-portal
```

**2. O programa** — copie `portal_vps.py` deste diretório (só ele; não precisa
de pip nem de venv, é biblioteca padrão do Python 3.10+).

```sh
install -o root -g root -m 644 portal_vps.py /opt/cartorio-portal/
python3 --version     # 3.10 ou mais novo
```

**3. O token** — longo e aleatório; é a senha da porta da VPS. O MESMO valor
vai depois na tela do sistema (Administrativo → Portal do cliente).

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))" > /etc/cartorio-portal/token
chown root:cartorio-portal /etc/cartorio-portal/token
chmod 640 /etc/cartorio-portal/token
cat /etc/cartorio-portal/token     # copie para levar ao oficial, por canal seguro
```

**4. A configuração** — copie `portal.env.exemplo` para
`/etc/cartorio-portal/portal.env` e preencha `PORTAL_SERVENTIA` e
`PORTAL_CONTATO` (o que aparece na página). Sem segredo nesse arquivo.

**5. O serviço** — copie `cartorio-portal.service` para
`/etc/systemd/system/` e ligue:

```sh
systemctl daemon-reload
systemctl enable --now cartorio-portal
systemctl status cartorio-portal
curl -s -H "X-Forwarded-Proto: https" http://127.0.0.1:8781/portal/ | head -5
```

**6. O Apache e o HTTPS** — o site do WhatsApp já tem certificado. Acrescente
o trecho de `apache-portal.conf` dentro do `<VirtualHost *:443>` dele:

```sh
a2enmod proxy proxy_http headers
apachectl configtest && systemctl reload apache2
```

Site novo, sem certificado: `apt install certbot python3-certbot-apache` e
`certbot --apache -d portal.exemplo.invalid` (o certbot cria o 443, o
redirecionamento do 80 e a renovação automática; confira com
`certbot renew --dry-run`). Com nginx no lugar do Apache, o equivalente é um
`location /portal/ { proxy_pass http://127.0.0.1:8781; proxy_set_header
X-Forwarded-Proto https; proxy_set_header X-Forwarded-For
$proxy_add_x_forwarded_for; client_max_body_size 25m; }`.

**7. O firewall** — só SSH, 80 (para o certbot renovar) e 443. A porta 8781
**não** se abre: o programa atende só em 127.0.0.1.

```sh
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status verbose
```

**8. Conferir de fora** — `https://portal.exemplo.invalid/portal/` abre o
formulário; um número qualquer com um código qualquer responde «não
conferem»; `http://` redireciona para `https://`.

## No servidor da serventia

1. **Administrativo → Portal do cliente**: endereço
   `https://portal.exemplo.invalid/portal`, o token do passo 3, e ligar o envio.
   O token fica no cofre (`portal.cred`), fora do banco.
2. **Enviar agora** — o «Último envio» tem de dizer quantos subiram.
3. **A tarefa do Agendador** (a TI instala), a cada 15 minutos, com a mesma
   conta e as mesmas variáveis do serviço (`CG_PG_DSN`, `PGPASSFILE`):

   ```bat
   "%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" portal_cliente.py --banco "<o banco da casa>"
   ```

   Ela imprime o resumo em JSON e sai com 0 (enviado, ou envio desligado).

## Atualizar e desfazer

- Atualizar: copiar o `portal_vps.py` novo e `systemctl restart cartorio-portal`.
- Desligar o portal sem mexer na VPS: desmarcar «Envio ligado» na tela. Para
  tirar tudo do ar: `systemctl disable --now cartorio-portal`, remover o trecho
  do Apache e apagar `/var/lib/cartorio-portal` (o banco só tem retratos; a
  verdade continua na serventia).
- Trocar o token: gerar outro no passo 3, `systemctl restart cartorio-portal`, e
  gravar o novo na tela do sistema.

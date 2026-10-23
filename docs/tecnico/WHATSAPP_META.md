# WhatsApp Cloud API — o que o oficial faz fora do código

02/09/2026 · Cartório Gestão 3.6.64 · Cidade Exemplo/MA

O Windows do Cartório Gestão **não vai para a internet**. Sem Cloudflare Tunnel, sem ngrok, sem abrir a porta 8765.

Caixa-postal: VPS Hostinger. Máquina `srv000000.exemplo.invalid` (80/443 Apache, 5222 XMPP). HTTP redireciona para **https://site-exemplo.invalid**. O certificado **não cobre** o nome `hstgr.cloud` — webhook e `caixa_url` usam o domínio do site (ou um subdomínio novo com TLS). Não usar `https://srv000000.exemplo.invalid`.

Worker Flask em **127.0.0.1** nessa VPS. Apache faz reverse proxy **somente** de `/whatsapp/webhook` e `/pendentes`. Não instalar nada no Windows do cartório para túnel. Deploy SSH do worker: o oficial ainda **não** pediu — este arquivo documenta; ninguém faz SSH nesta fatia.

HTTPS de *saída* do SERVIDOR (Graph para enviar rascunho; puxar a caixa) é permitido.

---

## 1. Conta Meta (navegador, o oficial)

1. Meta Business da **serventia** (não conta pessoal).
2. App em developers.facebook.com com produto WhatsApp / Cloud API.
3. Número de WhatsApp Business — **não o pessoal da escrevente**. Pode ser o (00) 90000-0000 se a Meta aceitar o chip da casa; senão número da Cloud API.
4. Anotar (colar na tela `/whatsapp/config`, nunca no código):
   - `verify_token` (o mesmo no worker da VPS)
   - `phone_number_id`
   - `access_token`
   - `app_secret` (HMAC). Sem secret, produção não deve expor webhook nenhum.

## 2. Worker na VPS (não neste Windows)

Flask mínimo em `127.0.0.1:8780`, **só** duas rotas:

| rota | quem chama | o que faz |
|---|---|---|
| `GET/POST /whatsapp/webhook` | Meta | GET: challenge com o mesmo `verify_token`. POST: guarda o JSON (HMAC se `app_secret`). |
| `GET /pendentes` | Cartório Gestão | lista os JSON ainda não puxados; `Authorization: Bearer <caixa_segredo>`. |

Não liga no banco do cartório. Esboço: `docs/tecnico/caixa_postal_xmpp_esboco.py` — copiar para a VPS quando o oficial pedir deploy; **não executar no SERVIDOR Windows**.

URLs públicas (TLS do site):

- Webhook Meta: `https://site-exemplo.invalid/whatsapp/webhook`
- Puxar (`caixa_url`): `https://site-exemplo.invalid/pendentes`

Alternativa de path se o Apache do site já ocupar a raiz: prefixo `/wa-caixa` (`https://site-exemplo.invalid/wa-caixa/whatsapp/webhook` e `.../wa-caixa/pendentes`).

Verify token = o da tela config.

Apache (VPS, esboço — não aplicar nesta fatia):

```
ProxyPreserveHost On
ProxyPass        /whatsapp/webhook  http://127.0.0.1:8780/whatsapp/webhook
ProxyPassReverse /whatsapp/webhook  http://127.0.0.1:8780/whatsapp/webhook
ProxyPass        /pendentes         http://127.0.0.1:8780/pendentes
ProxyPassReverse /pendentes         http://127.0.0.1:8780/pendentes
```

Só esses dois caminhos. O resto do site (site-exemplo.invalid) continua o Apache de sempre. Não proxy para o Cartório Gestão nem para 8765.

## 3. Cartório Gestão (já no código)

- Config: `/whatsapp/config` (login). Placeholder de `caixa_url` = `https://site-exemplo.invalid/pendentes`.
- Enviar rascunho aprovado: botão na conversa → Graph `https://graph.facebook.com/v21.0/{phone_number_id}/messages`.
- Puxar: botão na lista → GET em `caixa_url` (mock nos testes).
- Webhook local: só teste (`X-Wa-Test: 1`) ou HMAC. Não é a URL da Meta.

## 4. O que não fazer

- Não instalar cloudflared / túnel neste Windows.
- Não apontar nada para `127.0.0.1:8765` de fora.
- Não instalar o worker no SERVIDOR do Cartório Gestão.
- Não usar `srv000000.exemplo.invalid` na Meta (sem TLS nesse nome).
- Não fazer SSH / deploy nesta fatia.

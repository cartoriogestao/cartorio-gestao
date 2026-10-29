# Projeto — Balcão WhatsApp

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA — CNS 000000
02/09/2026 · versão 3.6.64 · oficial
Este arquivo é o projeto. Fatia 1 (fila + webhook de teste) e fatia 2 (config Meta + envio Graph + puxar da caixa-postal) estão no código. O SERVIDOR do Cartório Gestão **não** fica na internet.

O oficial disse «vamos fazer isso». Depois: o servidor do cartório **não** vai para a internet. A caixa-postal (worker) vai no **host XMPP da casa**, não neste Windows. Hostname do XMPP ainda estamos localizando — não inventar.

---

## O balcão que funciona sozinho (29/10/2026)

> «preciso que o whatsapp seja mais funcional, preciso que atualize em tempo real (se nao possivel com frequencia de 30s (se abrir uma janela ou aviso no windows), receba arquivos enviados na conversa, configure a IA para fazer o primeiro atendimento, passando para atendente quando houver justo motivo» — o oficial

Este trecho vale mais que o resto do arquivo quando os dois discordarem: as fatias abaixo descrevem como o balcão nasceu.

| o quê | onde | como |
|---|---|---|
| a mensagem chega em segundos | `wa_vigia` | uma linha de execução do próprio servidor busca a caixa-postal de 20 em 20 s (`vigia_segundos`), 24 h por dia; a automação de 2 em 2 min fica de reserva, e as duas juntas não dobram nada |
| o aviso no Windows | `static/whatsapp_atalho.js` | de 15 em 15 s (30 com a aba escondida, pelo relógio de um Worker): aviso do Windows (se a pessoa ligar), som, título piscando e cartão no canto |
| a hora certa | `wa_balcao.quando_da_meta` | a mensagem guarda a hora em que o cliente escreveu (o `timestamp` da Meta), e não a da puxada |
| ✓ ✓✓ lida, não chegou | `wa_balcao.aplicar_entregas` | os `statuses` da Meta, que eram jogados fora |
| os arquivos do cliente | `wa_midia` | foto, PDF, documento, áudio e vídeo são baixados e guardados em `<arquivos>/whatsapp/AAAA-MM/`; o balão mostra ou baixa (`/whatsapp/midia/<id>`) |
| mandar arquivo | `/whatsapp/<id>/arquivo` | sobe à Meta (`/media`) e envia, com legenda; a casa guarda a cópia |
| a IA no primeiro atendimento | `wa_atendente` (rodado pelo vigia) | as regras de 26/10, e mais duas de passagem: o cliente mandou arquivo; o cliente seguiu escrevendo depois de 4 respostas automáticas |
| horário e fora do horário | `wa_horario`, `wa_rotina` | o aviso de passagem diz quando a casa responde; o aviso de fora do horário sai uma vez por período fechado |
| respostas prontas | `wa_rotina.ler_respostas` | «atalho \| texto», com {nome} |
| conversa parada | `wa_rotina.encerrar_paradas` | respondida e sem volta do cliente há N dias (padrão 3) → resolvida, com o rastro |

**O aviso automático não é resposta.** O aviso de passagem e o de fora do horário saem com `tipo='aviso'`: não contam no «esperando resposta», nem no tempo da primeira resposta, e não põem a conversa em «aguardando». Até 29/10/2026 contavam, e a conversa que a IA passava para uma pessoa sumia do alerta.

**O aviso do Windows exige endereço seguro.** O navegador só libera a notificação do sistema em `https` ou no próprio servidor (`127.0.0.1`); nos balcões em `http://<ip>:8765` ficam o som, o título e o cartão, até o Chrome receber a política `OverrideSecurityRestrictionsOnInsecureOrigin` com o endereço do servidor (ou o sistema ganhar `https` na rede).

**A FAZER:** feriado no horário; vincular a conversa a protocolo e cliente; a pesquisa de satisfação ao resolver (o modelo da Meta já existe, falta a aprovação).

---

## O que o oficial pediu

Atender o público pelo WhatsApp, com o Cartório Gestão no meio — não um programa paralelo. Sem expor a porta 8765. Sem túnel no SERVIDOR.

## O que isto NÃO é

**Não é WhatsApp Web, Baileys nem Evolution.** Decisão fechada: API **oficial** Meta Cloud API.

**Não é BSP nesta fatia.** 360dialog e Twilio ficam de fora. Sem Chatwoot e sem n8n: a fila vive **dentro** do Cartório Gestão.

**Não é modelo pago nesta fatia.** Classificador + rascunho por regras. Autoenvio **desligado**.

**Nunca autoenviar:** CPF, valor, protesto, certidão, instrumento, dado de livro.

**Não inventa horário de expediente.**

**Não instala túnel, cloudflared, ngrok nem worker neste Windows.** Não copiar `Program Files`. Não rodar `ATUALIZAR_SISTEMA` nesta fatia.

---

## Arquitetura (fatia 2) — o SERVIDOR só sai, não entra

```
  cliente WhatsApp
        |
        v
     Meta Cloud API
        |
        |  webhook HTTPS
        v
  worker Flask 127.0.0.1:8780  ←  VPS Hostinger
  Apache (site-exemplo.invalid) proxy SÓ:
    GET/POST /whatsapp/webhook
    GET      /pendentes   (Bearer caixa_segredo)
  (alternativa de path: /wa-caixa/...)
        ^
        |  HTTPS de saída (puxar)
        |
  Cartório Gestão  (Windows, 127.0.0.1:8765, SEM túnel)
    tela /whatsapp
    POST Graph para ENVIAR rascunho aprovado
```

O Flask do Cartório Gestão ainda tem `GET/POST /whatsapp/webhook` **só para teste local** (`X-Wa-Test: 1`) e para o dia em que a caixa-postal reenviar com HMAC. Em produção o inbound **não** chega direto. Sem `app_secret`, o POST daqui não abre para o mundo.

Detalhe operacional: `docs/tecnico/WHATSAPP_META.md`. Esboço do worker: `docs/tecnico/caixa_postal_xmpp_esboco.py` — **instalar no XMPP, nunca neste Windows.**

---

## Regras da casa que este projeto não fura

- Módulo de domínio primeiro; rota só liga.
- `MIGRACOES` só `ALTER TABLE ADD COLUMN`. Tabela nova vai no `SCHEMA`.
- `audit()` fora de `db.transaction()`.
- GET não escreve (salvo o challenge do webhook, que só devolve texto).
- Segredo da Meta **nunca** no código: `wa_config` começa vazio. Nunca logar token.
- Dado pessoal não sai em relatório de problema.
- `ATUALIZAR_SISTEMA` não roda nesta fatia. Não se copia `Program Files`.

---

## Parte código

### Fatia 1 — a fila existe, o webhook aceita POST local

Arquivos: `wa_schema.py`, `wa_textos.py`, `wa_balcao.py`, `wa_web.py`, templates `whatsapp_*.html`, `tests/test_wa_balcao.py`.

Tabelas: `wa_conversa`, `wa_mensagem`, `wa_config`.

Rotas: `GET/POST /whatsapp/webhook` (sem login, CSRF isento), `GET /whatsapp`, `GET /whatsapp/<id>`, `POST .../rascunho`, `POST .../resolver`.

Menu: Administrativo → Atendimento → **WhatsApp**.

### Fatia 2 — config + envio + puxar (sem expor o SERVIDOR)

Arquivos a mais: `wa_puxar.py`, `templates/whatsapp_config.html`, `docs/tecnico/WHATSAPP_META.md`, esboço do worker.

`wa_config` chaves: `verify_token`, `app_secret`, `phone_number_id`, `access_token`, `caixa_url`, `caixa_segredo`.

Rotas:

- `GET/POST /whatsapp/config` — login. access_token mascarado (últimos 4); campo vazio = não altera. verify_token gravado passa a valer no GET webhook local (vazio = `cartorio-teste`).
- `POST /whatsapp/<id>/enviar` — Graph `v21.0/{phone_number_id}/messages`. Timeout curto. Só com token + phone + rascunho. Sucesso: `wa_mensagem` direcao=out, status `aguardando`, rascunho permanece na thread. Falha: erro na tela, não inventa envio. Autoenvio desligado.
- `POST /whatsapp/puxar` — busca `caixa_url` (host XMPP). Sem URL: avisa. Testes mockam a rede.
- Webhook POST: se `app_secret` gravado, exige HMAC `X-Hub-Signature-256`; senão só `X-Wa-Test: 1`.

O que o oficial preenche na tela (quando tiver): verify_token, phone_number_id, access_token, app_secret (HMAC), e `caixa_url` (`https://site-exemplo.invalid/pendentes`) + `caixa_segredo`.

O que ainda falta (oficial no navegador; deploy SSH **ainda não pedido**): conta Meta Business, app Cloud API, número (não o pessoal da escrevente), worker na VPS atrás do Apache, colar `caixa_url` se ainda estiver vazia.

### Fatia 3 — modelo (opcional)

Classificador e rascunho por modelo pago, se o oficial quiser. Autoenvio continua desligado.

---

## Prova da fatia 2

- GET `/whatsapp/config` exige login.
- POST config grava verify_token; GET webhook com o token novo devolve challenge; token errado 403.
- POST enviar com urllib mockado cria mensagem `out`.
- POST enviar sem token: 4xx, não chama rede.
- HMAC certo aceita; errado 403.
- Puxar com `http_get` mockado aplica pendente. Sem bater na Meta nem no XMPP.

Simular entrada local (sistema no ar **ou** só o teste):

```
curl -s -D - -o - -X POST "http://127.0.0.1:8765/whatsapp/webhook" ^
  -H "Content-Type: application/json" ^
  -H "X-Wa-Test: 1" ^
  -d "{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"contacts":[{"profile":{"name":"Teste"},"wa_id":"5500000000000"}],"messages":[{"from":"5500000000000","id":"wamid.local-1","type":"text","text":{"body":"Qual o horario de voces?"}}]}}]}]}"
```

---

## O que este projeto de código recusa

- Evolution, Baileys, WhatsApp Web, Chatwoot, n8n, BSP nesta fatia
- Hardcode de `access_token` / `app_secret`
- Autoenvio, inclusive de horário inventado
- Túnel / cloudflared / ngrok no SERVIDOR do Cartório Gestão
- Instalar o worker neste Windows
- Expor a porta 8765
- Usar srv000000.exemplo.invalid sem TLS; fazer SSH nesta fatia
- `ATUALIZAR_SISTEMA` antes do teste desta fatia estar verde
- Mexer em `C:\Program Files\CartorioGestao` por cima do instalado

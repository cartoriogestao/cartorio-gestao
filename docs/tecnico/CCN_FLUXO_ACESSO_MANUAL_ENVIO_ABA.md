# CCN — fluxo ACESSO MANUAL + ENVIO AUTOMÁTICO (na aba do usuário)

**Ofício Único de Cidade Exemplo/MA · CNS 000000 · Cartório Gestão (sandbox)**  
**Data:** 2026-10-05 · **Decisão do oficial:** acesso manual no portal + envio automático **dentro da sessão do navegador**.  
**Escopo:** só documentação + esqueleto de ensaio em `SANDBOX\sistema\ccn_assistente\`.  
**Não** há cliente CCN no Flask. **Não** reinicia `:8899`. **Não** toca produção.

Documentos irmãos:

- `CCN_BLOQUEIO_E_ALTERNATIVAS.md` — por que Cloudflare + CAdES travam o caminho servidor
- `PLANO_A3_NOTAS_IMOVEIS.md` — marcos A3-0…A3-5
- `docs/tecnico/A3_SERVICO_LOCAL.md` — serviço `127.0.0.1:8766`
- `TRAVA_NOTAS_RI_HOSTS.md` — homolog liberada; produção CCN deny no sandbox

---

## 1. Em uma frase (para o oficial)

O escrevente **entra sozinho** no portal CCN/e-Notariado (passa Cloudflare e login A3/SafeID normalmente). Depois disso, um **assistente no próprio navegador** monta o pedido, pede a assinatura `X-Signature` ao serviço A3 local (`127.0.0.1:8766`) e **envia o fetch na mesma aba** — sem cookie no Flask, sem bypass Cloudflare, sem PKCS#11 no balcão.

---

## 2. Por que extensão MV3 (e não página auxiliar)

| Opção | Prós | Contras neste desenho |
|---|---|---|
| **Extensão Chrome MV3** (escolhida) | Content script age **só** em `pessoas-hml.e-notariado.org.br`; `fetch` com `credentials: "include"` na **mesma origem** da aba; background chama `127.0.0.1:8766` sem CORS da página; host permissions explícitos | Precisa instalar em modo desenvolvedor no ensaio |
| Página auxiliar estática (file:// ou :8899) | Mais simples de abrir | Cross-origin: **não** compartilha cookie da sessão CCN; não consegue “enviar na aba” sem gambiarra; pior alinhamento com a regra 2 do oficial |

**Decisão:** esqueleto = **extensão MV3** em `ccn_assistente/extensao/`. Página auxiliar cross-origin foi descartada para o ensaio realista.

---

## 3. Diagrama textual

```
┌─────────────────────────────────────────────────────────────┐
│  Navegador do usuário (Chrome/Edge)                         │
│                                                             │
│  ① Usuário abre https://pessoas-hml.e-notariado.org.br      │
│     → passa Cloudflare (JS humano)                          │
│     → login A3/SafeID no portal                             │
│                                                             │
│  ② Extensão CG CCN Assistente (MV3)                         │
│     ┌─ content script (só host homolog) ─────────────────┐  │
│     │  monta payload / path da API                       │  │
│     │  pede assinatura ao background                     │  │
│     │  fetch(API, { credentials:"include", headers… })   │  │
│     │  ← cookie/sessão ficam NO NAVEGADOR                │  │
│     └────────────────────────────────────────────────────┘  │
│                    │ chrome.runtime message                 │
│                    ▼                                        │
│     ┌─ service worker (background) ──────────────────────┐  │
│     │  POST http://127.0.0.1:8766/assinar/cades          │  │
│     │  (contrato stub → A3-3; hoje A3-1 só tem /pdf)     │  │
│     │  devolve x_signature_b64                           │  │
│     └────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                            │ só assinatura (bytes)
                            ▼
              ┌─────────────────────────────┐
              │ a3_servico_local.py         │
              │ 127.0.0.1:8766              │
              │ → a3_assinador_filho (PKCS) │
              │ PIN na hora; sem .cred      │
              └─────────────────────────────┘

┌─────────────────────────────────────────┐
│ Cartório Gestão Flask (:8899 sandbox)   │
│  • NÃO chama a API CCN                  │
│  • NÃO recebe cookie/token do portal    │
│  • Pode, no futuro, só preparar JSON    │
│    de cadastro para o assistente colar  │
│    (fora deste esqueleto)               │
│  • assinar_com_a3 = camada CG→A3        │
│    (PDF hoje; CAdES quando A3-3)        │
└─────────────────────────────────────────┘
```

---

## 4. Papéis

| Peça | O que faz | O que NÃO faz |
|---|---|---|
| **Navegador do usuário** | Cloudflare + login portal + cookie de sessão | — |
| **Extensão MV3** (`ccn_assistente/extensao`) | Content script só em homolog; monta headers; `fetch` na aba; pede CAdES ao localhost | Bypass Cloudflare; roubar cookie para o servidor; falar com produção CCN |
| **Serviço A3 local** (`a3_servico_local.py` :8766) | Assina bytes (PDF hoje; CAdES no contrato A3-3) via filho isolado | Bind em `0.0.0.0`; gravar PIN; chamar e-Notariado |
| **`assinar_com_a3.py`** | Único ponto Flask→localhost A3 (ensaio PDF / status) | Cliente CCN; carregar PKCS#11 |
| **CG Flask (:8899)** | Balcão; no futuro pode exportar rascunho JSON para o assistente | Cliente HTTP CCN; reaproveitar cookies; PKCS#11 no processo |

---

## 5. Sequência passo a passo (ensaio)

1. No SERVIDOR sandbox: `py -3 a3_servico_local.py` (porta **8766** no ar).  
2. Chrome/Edge → `chrome://extensions` → Modo do desenvolvedor → **Carregar sem compactação** → pasta `SANDBOX\sistema\ccn_assistente\extensao`.  
3. Usuário abre **homolog**: `https://pessoas-hml.e-notariado.org.br` e completa Cloudflare + login A3/SafeID.  
4. Na aba homolog, o content script mostra o painel do assistente (ensaio).  
5. Usuário escolhe operação de ensaio (ex.: montar payload de exportação / importação **mock** — sem inventar credencial).  
6. Background chama o contrato `POST /assinar/cades` em `127.0.0.1:8766` com o JSON a assinar + PIN digitado no popup/painel (efêmero).  
7. Com `X-Signature` (e, quando houver, `X-Api-Key` / `X-Subscription` vindos da UI/`centrais_cred` — **nunca inventados**), o content script faz `fetch` **na origem da aba** com `credentials: "include"`.  
8. Resposta fica na aba; **nenhum** Set-Cookie ou Authorization é enviado ao Flask.

### Homolog vs produção

| Ambiente | Host | Sandbox |
|---|---|---|
| **Homolog (ensaio)** | `pessoas-hml.e-notariado.org.br` | Liberado na trava; **único** host da extensão neste marco |
| **Produção** | `pessoas.e-notariado.org.br` | **Deny** na trava sandbox; extensão **não** declara esse host |

---

## 6. O que fica no browser vs no servidor

| Dado | Onde fica |
|---|---|
| Cookie / sessão Cloudflare + portal | **Só no navegador** |
| PIN do token A3 | Digitado na hora no painel/popup → vai ao `:8766` → filho → apagado; **nunca** `.cred`/banco/log/chat |
| Payload CAdES a assinar | Montado no content script; bytes enviados ao serviço local |
| `X-Signature` (base64) | Voltando do serviço A3 → header do `fetch` na aba |
| `X-Api-Key` / AppToken / `X-Subscription` | Quando existirem: UI `/configuracoes` + ProgramData `*.cred` / `centrais_cred` — **pendente**; assistente lê só o que o usuário colar no painel de ensaio ou o que a UI autorizar depois |
| Cadastro/rascunho do ato no CG | Banco sandbox do Cartório Gestão (sem transporte CCN neste esqueleto) |

---

## 7. Contrato stub A3 (payload → assinatura)

Arquivo: `ccn_assistente/contrato/assinar_cades_ccn.stub.json`

Hoje o serviço A3-1 só expõe `POST /assinar/pdf`. O assistente já fala a linguagem do **futuro** `POST /assinar/cades` (marco A3-3), alinhada a `assinar_com_a3` / serviço local:

**Pedido (conceito):**

```json
{
  "op": "assinar_cades",
  "payload_utf8": "{\"Timestamp\":\"2026-10-05T19:00:00Z\",\"RequestPath\":\"/api/exports/record-sets/00000000000\"}",
  "pin": "(só na hora — nunca neste arquivo de exemplo)",
  "thumbprint": null
}
```

**Resposta (conceito):**

```json
{
  "ok": true,
  "formato": "CAdES-BES-detached",
  "x_signature_b64": "<base64 da assinatura para header X-Signature>",
  "assinatura_b64": "<mesmo ou CMS>",
  "subject": "...",
  "thumbprint": "..."
}
```

Até o A3-3 existir de verdade, o background da extensão trata `404`/`erro` do `/assinar/cades` como **“serviço ainda sem CAdES — rode A3-1 PDF e aguarde marco A3-3”**, sem fingir sucesso de rede CCN.

---

## 8. Riscos e o que NÃO fazer

| Proibido | Motivo |
|---|---|
| Bypass / furar Cloudflare (scrapers de challenge, emular JS só para burlar) | Fora do contrato; a casa não implementa |
| Reaproveitar cookies/tokens **fora** do navegador do usuário (Flask, scripts servidor) | Quebra a regra 2 do oficial; sessão não é do servidor |
| Robô servidor passando pelo challenge | Medido: 403 `Cf-Mitigated: challenge` |
| Carregar PKCS#11 no Flask | Segfault 139 → cai o balcão |
| Cliente CCN em `app.py` / `notas_web` / `ri_web` neste marco | Proibido pelo pedido; trava + honestidade |
| Inventar `X-Api-Key` / colar PIN em chat | Credencial só via UI/ProgramData; PIN efêmero |
| Apontar ensaio para `pessoas.e-notariado.org.br` no sandbox | Produção bloqueada pela trava |

---

## 9. Dependências

| Dependência | Status |
|---|---|
| **A3-1** serviço `127.0.0.1:8766` (`a3_servico_local.py` + filho + `assinar_com_a3.py`) | Código no sandbox; ensaio manual com token pendente |
| Extensão MV3 `ccn_assistente` | Esqueleto deste marco |
| Rota `POST /assinar/cades` no serviço local | **Pendente A3-3** (contrato stub já desenhado) |
| Credenciais CCN (`X-Api-Key` / AppToken / `X-Subscription`) | **Pendentes** — cadastrar em `/configuracoes` + `centrais_cred` quando a central liberar; **nunca inventar** |
| Allowlist CNB server-to-server | Caminho paralelo (rascunho pedido CNB); **não** substitui este fluxo assistido |

---

## 10. Onde está o código de ensaio

```
SANDBOX\sistema\ccn_assistente\
  README.md                 ← como instalar/usar no ensaio
  contrato\
    assinar_cades_ccn.stub.json
  extensao\
    manifest.json           ← MV3; host_permissions só homolog + localhost
    background\service_worker.js
    content\content.js
    content\painel.css
    popup\popup.html
    popup\popup.js
```

Cópia de apoio no box: `/workspace/sandbox-alteracoes/CCN_FLUXO_ACESSO_MANUAL_ENVIO_ABA.md` e `ccn_assistente/`.

---

## 11. Critério de sucesso deste marco

- [x] Documento de arquitetura em português (oficial + dev)  
- [x] Esqueleto extensão utilizável em ensaio (sem bypass, sem cookie no Flask)  
- [x] Contrato stub JSON documentado  
- [x] REGISTRO_ALTERACOES_SANDBOX  
- [ ] Ensaio ao vivo com token + PIN + homolog (oficial) — **fora** deste entregável de código  
- [ ] A3-3 CAdES real no serviço local — **próximo marco**

---

*Criado em 2026-10-05. Não altera `notas_web` / `ri_web` / `atribuicoes_web` / modelos / produtividade. Não reinicia `:8899`. Não toca produção (:8765 / Program Files).*

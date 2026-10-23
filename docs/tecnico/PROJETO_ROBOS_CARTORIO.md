# Projeto - Robôs do Cartório

Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA - CNS 000000
07/09/2026 — oficial
Este arquivo é o projeto. O SERVIDOR do Cartório Gestão **não** fica na internet.

---

## PIVÔ 2026-09-07 — novo modelo (cérebro = Grok Bot)

**Mudança de arquitetura:** o cérebro do robô **não** é mais o módulo Flask `/robos`. Cada robô completo é um **assistente Grok Bot** (mesmo tipo de poderes que o «teste cart»): um agente Cursor por tipo de ato, com capacidade de ler/agir no contexto do cartório sob humano no loop.

### 1. Robô completo = assistente Grok Bot

- Um Grok Bot por ato (certidão RCPN, firma, protesto, proclamas…).
- Mesmo tipo de poderes que o assistente de teste cart: ferramentas, leitura de arquivos/contexto, execução sob regras da casa.
- Treino / especialização = prompt + exemplos + instruções do agente — **não** fine-tune nesta fase.
- Humano no loop: o agente sugere / prepara; oficial ou escrevente decide. **Nunca** autoenviar dado de livro. **Nunca** gravar sozinho no RCPN/RI/protesto/notas. **Nunca** autoenviar WhatsApp.


### 2b. Robôs criados 2026-09-07 (um por ato — oficiais ensinam depois)

| Nome | Id | Ato |
|---|---|---|
| Robô Certidão RCPN | `76d5175b-3639-4027-93ee-32f53de4db50` | Certidão RCPN (já existia) |
| Robô Nascimento RCPN | `844c6b1d-3355-43af-980c-a7717ee0cbd8` | Nascimento |
| Robô Casamento RCPN | `6c58584b-6de5-4fdc-beba-f5d1d83c5846` | Casamento / habilitação |
| Robô Óbito RCPN | `4d097892-3a47-4a5a-afe7-ea8df03dfecb` | Óbito |
| Robô Proclamas | `11dc7d6c-7f20-4b1e-b032-f99e9ec7ad6c` | Proclamas |
| Robô Firmas | `a4b5bdcd-cf21-401e-9f26-e613c52f2846` | Firma / biometria #39 |
| Robô Protesto | `6fd60c1f-a63d-4702-b677-1f80141900a7` | Protesto |
| Robô Tabelionato de Notas | `3a4ae7c3-6a2b-4541-bc17-8f9cad991aef` | Notas |
| Robô Registro de Imóveis | `3ea26b31-8d89-48cf-81b1-bcb1ab3dcf3f` | RI |
| Robô RCPJ e RTD | `53a6c80b-d1ce-4513-895d-7fadabcd5217` | RCPJ e RTD |
| Robô escrevente (Substituta) | `13f01235-40ae-4390-954b-c5b58ffc38de` | Person bot — CG user `beatriz` (id 2), Substituta, full balcão |
| Robô escrevente | `94935927-8020-43c0-9d77-81575a88f0a6` | Person bot — CG user `gabriela` (id 5), Escrevente Autorizada, full balcão |
| Robô escrevente | `0e06fe87-83c3-4d9a-a6df-811e29a16f16` | Person bot — CG user `daniela` (id 6), Escrevente Autorizada, full balcão |
| Robô escrevente | `35306072-bec1-45aa-b6f4-52a2f3ccc0ca` | Person bot — CG user `pedro` (id 4), Auxiliar, full balcão |
| Robô escrevente | `5e43c1bf-18a3-489e-8f34-42fc89a916e2` | Person bot — CG user `carla` (id 3), Escrevente Autorizada, full balcão |
| Robô WhatsApp Balcão | `34a8c156-a5f7-4b88-927f-f3b61b040103` | WhatsApp Cloud API |

Todos na mesma conta Cursor da serventia. Oficial edita descrição e ensina um por um na conversa de cada agente.

### 2c. Person robots ↔ Cartório Gestão users (2026-09-30)

Person robots are **Grok Bot agents**, not Flask `/robos` brains. They act with the **human** `users` row (same USER role / balcão powers). Do **not** create CG users named `Robô …` (`nome_humano` blocks robot labels on selo).

Canonical map in production DB settings key **`grok_bot_personas`** (JSON). Also mirrored as rows in table `robo` (painel `/robos`, optional). SERVIDOR machineId: `00000000-0000-0000-0000-000000000000`. When inserting via SQL/Flask test client, set `session["user_id"]` / audit username to the mapped human user — never the robot display name.

### 2. Primeiro criado: Robô Certidão RCPN

| Campo | Valor |
|---|---|
| Nome | **Robô Certidão RCPN** |
| Id do agente | `76d5175b-3639-4027-93ee-32f53de4db50` |
| Ato | Certidão de Registro Civil de Pessoas Naturais |

Este é o primeiro robô no novo modelo. Os demais (firma, protesto, etc.) virão em fatias futuras.

### 3. Módulo Flask `/robos` (3.6.67) = fila/painel **opcional**

O código Flask da fatia 1 (versão 3.6.67) **permanece** no projeto. Nesta tarefa **não** se remove código Flask.

Papel atualizado:

- Cadastro de **qual agente** cuida de **qual ato** + pedido / fila.
- Painel opcional de acompanhamento (lista, status, vínculo agente↔ato).
- Fila que **acorda** o agente do ato quando chega pedido.
- **NÃO** é o cérebro do robô. A geração/raciocínio fica no Grok Bot (agente), não em `robo_llm` / `chamar_provedor` como motor principal.

Ou seja: `/robos` = fila/painel; Grok Bot = robô.

### 4. Acesso compartilhado — TODOS os computadores do cartório

**Requisito do oficial:** todos os PCs da serventia precisam usar os robôs.

Como:

- Acesso compartilhado = **Cartório Gestão na LAN**: `http://SERVIDOR:8765` (hostname ou IP do SERVIDOR na rede local).
- Login **existente** do Cartório Gestão (mesmo usuário/senha de sempre).
- `/robos` = fila/painel que cadastra o pedido e **acorda** o agente do ato.
- **Grok Bot** na mesma conta da serventia é **opcional por estação** (não é obrigatório ter Cursor/Grok Bot em cada PC para pedir via `/robos`).
- **NUNCA** expor na internet: sem túnel, sem cloudflared, sem ngrok, sem port-forward público. Só LAN da casa.

### 5. Fatias futuras

- Fila no Cartório Gestão que **acorda** o agente certo quando chega pedido do ato (já esboçada no papel de `/robos`).
- Mais robôs: firma, protesto, proclamas, outros…
- Continua: **nunca** autoenviar dado de livro; nunca gravar no livro sem confirmação humana; nunca autoenviar WhatsApp; nunca túnel no SERVIDOR; nunca mexer em `Program Files` sem instalador; não rodar `ATUALIZAR_SISTEMA` sem ordem explícita.

---

## O que o oficial pediu (contexto original + pivô)

Gerenciar robôs de atendimento/rascunho **dentro** do ecossistema Cartório Gestão — não um programa paralelo solto. Cada robô = um tipo de ato. No modelo antigo (3.6.67) isso era CRUD + LLM via Flask. No **pivô 2026-09-07**, cada robô = um Grok Bot; o Flask `/robos` fica como fila/painel opcional acessível na LAN por todos os PCs.

O escrevente / oficial testa e confirma; o sistema **não** lança sozinho no livro nem no WhatsApp.

## O que isto NÃO é

**Não é fine-tune nesta fatia.** Treino = prompt + exemplos / instruções do agente.

**Não é gravação no livro.** Nada vai para RCPN, RI, protesto, notas sem confirmação humana. Nunca autoenviar dado de livro.

**Não é autoenvio de WhatsApp.** O balcão WhatsApp continua com autoenvio desligado; este módulo/agentes não mandam mensagem sozinhos.

**Não remove o Flask `/robos` nesta tarefa.** Só documenta o pivô: Flask = fila/painel; cérebro = Grok Bot.

**Não é exposição na internet.** Acesso só na LAN (`http://SERVIDOR:8765`). Sem túnel.

**Não copia `Program Files`.** Não roda `ATUALIZAR_SISTEMA` sem ordem explícita.

---

## Arquitetura (visão — pós-pivô 2026-09-07)

```
  PCs do cartório (TODOS, LAN)
        |
        v
  http://SERVIDOR:8765  (Cartório Gestão, login existente)
        |
        +-- /robos  = fila/painel (cadastro agente↔ato + pedido)
        |     acorda o agente do ato
        |     NÃO é o cérebro
        |
        v
  Grok Bot (cérebro; um agente por ato)
        primeiro: Robô Certidão RCPN
        id: 76d5175b-3639-4027-93ee-32f53de4db50
        (poderes tipo teste cart)
        Grok Bot na conta da serventia = opcional por estação

  NUNCA internet / túnel
  NUNCA autoenviar dado de livro

  (fatias futuras)
  mais robôs: firma, protesto…
```

Visão legada (fatia 1 Flask, ainda no código, agora só painel/fila):

```
  Flask /robos
    CRUD robô + exemplos
    config de chaves (mascaradas)
    POST testar → rascunho (legado; cérebro migra para Grok Bot)
  SQLite: robo, robo_exemplo, robo_config, robo_teste_log
```

O SERVIDOR só sai à rede externa se houver chave e alguém pedir teste explícito no painel legado. Nos testes automatizados a rede é **sempre mock**. Acesso operacional dos PCs = **somente LAN**.

---

## Regras da casa que este projeto não fura

- Módulo de domínio primeiro; rota só liga.
- `MIGRACOES` só `ALTER TABLE ADD COLUMN`. Tabela nova vai no `SCHEMA`.
- `audit()` fora de `db.transaction()`.
- GET não escreve.
- Chave de API **nunca** no código: `robo_config` começa vazio. Nunca logar API key.
- LGPD: log de quem testou (`robo_teste_log.usuario`); não logar chaves.
- Humano no loop: rascunho/sugestão; oficial/escrevente decide.
- `ATUALIZAR_SISTEMA` não roda sem ordem. Não se copia `Program Files`.
- **Nunca autoenviar dado de livro.**
- **Nunca expor na internet** (só LAN).

---

## Provedores (legado do painel Flask 3.6.67)

| id | nome na tela | endpoint (chat completions) |
|---|---|---|
| `grok` | Grok (xAI) | `https://api.x.ai/v1/chat/completions` |
| `gpt` | GPT (OpenAI) | `https://api.openai.com/v1/chat/completions` |
| `claude` | Claude (Anthropic) | `https://api.anthropic.com/v1/messages` |
| `deepseek` | DeepSeek | `https://api.deepseek.com/chat/completions` |

Chaves em `robo_config`: `api_key_grok`, `api_key_gpt`, `api_key_claude`, `api_key_deepseek`, `provedor_padrao`. Vazio na tela = não altera. UI mostra mascarado (últimos 4). No pivô, o cérebro preferencial é o **agente Grok Bot**, não estas chamas HTTP como motor principal.

---

## Parte código

### Fatia 1 — CRUD + config + testar (local/mock) — entregue; agora painel/fila

Arquivos: `robo_schema.py`, `robo_llm.py`, `robo_web.py`, templates `robos_*.html`, `tests/test_robos.py`.

Tabelas: `robo`, `robo_exemplo`, `robo_config`, `robo_teste_log`.

Rotas (login):

- `GET /robos` — lista
- `GET/POST /robos/novo`
- `GET/POST /robos/<id>` — editar (nome, ato, provedor, prompt, ativo)
- `POST /robos/<id>/exemplos` — adicionar; `POST .../exemplos/<eid>/apagar`
- `GET/POST /robos/config` — chaves mascaradas
- `POST /robos/<id>/testar` — pedido → rascunho + log

Menu: Administrativo → Atendimento → **Robôs**.

Runtime sem chave: eco do prompt + pedido (+ exemplos), aviso «sem chave — modo local». Com chave: stub HTTP preparado; testes mockam `chamar_provedor`.

**Pós-pivô:** este módulo permanece como fila/painel opcional (vínculo agente↔ato + pedido que acorda o agente). Acessível na LAN por todos os PCs via `http://SERVIDOR:8765`. Não remover nesta tarefa.

### Fatia 2 — Grok Bot por ato (em curso)

- Robô = assistente Grok Bot (poderes tipo teste cart).
- Primeiro: **Robô Certidão RCPN** — agente `76d5175b-3639-4027-93ee-32f53de4db50`.
- Flask `/robos` só cadastra/acompanha/acorda; não é cérebro.
- Grok Bot na conta da serventia = opcional por estação.

### Fatia 3 — fila no CG que acorda o agente

- Pedido no Cartório Gestão (qualquer PC na LAN) → `/robos` → acorda o agente do ato.
- Nunca instalar túnel no SERVIDOR. Nunca expor na internet.

### Fatia 4 — mais robôs + livro com humano no loop

- Mais robôs: firma, protesto, proclamas…
- Sugerir texto **só como rascunho**; oficial confirma antes de qualquer gravação.
- **Nunca** autoenviar dado de livro. Continua sem autoenviar WhatsApp.

### Fatia N — opcional

- Fine-tune / embeddings se o oficial quiser.
- Integração explícita com a fila WhatsApp (rascunho aprovado manualmente).

---

## Prova da fatia 1 (legado Flask)

- Schema cria as quatro tabelas.
- Criar robô + exemplo.
- `rascunhar` em modo local sem chave.
- Config não vaza chave completa no HTML (mascarada).
- Rota de testar exige login.

```
C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe -m pytest tests/test_robos.py -q
```

(rodar na pasta fonte `INSTALAR_CARTORIO_GESTAO`; **não** `ATUALIZAR_SISTEMA` sem ordem.)

---

## O que este projeto recusa

- Fine-tune / SDK pesado sem ordem
- Hardcode de API key
- Gravar rascunho de teste no livro/RCPN sem confirmação
- Autoenviar dado de livro
- Autoenvio WhatsApp
- Logar API key
- Túnel / cloudflared / ngrok / exposição na internet
- `ATUALIZAR_SISTEMA` sem ordem explícita
- Mexer em `C:\Program Files\CartorioGestao` por cima do instalado
- Tratar o Flask `/robos` como cérebro do robô após o pivô 2026-09-07

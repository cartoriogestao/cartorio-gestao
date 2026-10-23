# CCN — bloqueio (Cloudflare + A3) e alternativas honestas

**Para o oficial** · Ofício Único de Cidade Exemplo/MA · Cartório Gestão (sandbox)  
**Data:** 2026-10-05 · **Só documentação** — nenhum cliente CCN novo foi ligado.

Este texto resume, em português simples, **por que a integração automática com o CCN ainda não sobe**, o que o plano A3 resolve e o que **não** resolve, e quais caminhos são honestos. Não inventa transporte. Não promete tela que “funciona” sem rede + assinatura.

Documentos irmãos (leitura técnica já medida):

- `O_CCN_E_AS_DUAS_PAREDES.md` — medição das duas paredes
- `ASSINATURA_DIGITAL_A3.md` — por que PKCS#11 no Flask derruba o balcão
- `PEDIDO_DAS_CREDENCIAIS.md` — CCN **não** é “falta colar a chave”
- Manual de chaves Notas/Imóveis (seção e-Notariado/CCN)
- Plano A3 (box): `/workspace/sandbox-alteracoes/PLANO_A3_NOTAS_IMOVEIS.md`

---

## 1. O que é o CCN

O **CCN** (Cadastro Único de Clientes do Notariado) é o módulo do **e-Notariado** (Provimento CNJ 149/2023): base nacional de **pessoas** (dados biográficos, documentos e biometria).

| | |
|---|---|
| **Não é** | lavratura de escritura, registro ou selo |
| **É** | cadastro que o tabelionato **alimenta** (importação) e **consulta** (exportação / CPF) |
| Homologação | `https://pessoas-hml.e-notariado.org.br` |
| Produção | `https://pessoas.e-notariado.org.br` |
| Autenticação típica | `X-Api-Key` (ou AppToken) + `X-Subscription` (Id do Cartório) |

Na prática da casa há **duas metades**:

| Meio | Para quê | Exige além da chave |
|---|---|---|
| **Importação** (maioria das operações) | subir cadastros do cartório | passar pela rede (hoje: Cloudflare) |
| **Exportação** (consulta por CPF) | buscar pessoa na base nacional | rede **e** cabeçalho `X-Signature` = assinatura **CAdES** da requisição |

**Hoje não há linha CCN em `centrais_cred` / tela que finja API funcionando.** Isso é de propósito: a chave sozinha não abre as duas paredes abaixo.

---

## 2. Parede 1 — Cloudflare

Medido na **rota da API** (não só no swagger):

```
GET .../api/imports  →  HTTP 403
Server: cloudflare
Cf-Mitigated: challenge
corpo: «Just a moment...»
```

| Quem chama | Resultado |
|---|---|
| Cliente do sistema (`http.client` / servidor) | **403** (challenge) |
| Mesmo cliente com cabeçalhos de navegador “completos” | **403** (challenge) |
| Navegador humano (com JavaScript) | **200** |

**Não é “falta User-Agent”.** O desafio exige executar JavaScript. Integração servidor-a-servidor bate nessa parede **antes de qualquer credencial**.

Sem liberação oficial do CNB-CF (allowlist de IP, canal server-to-server, ou host de API sem challenge), **importação automática pelo Cartório Gestão não sobe**.

---

## 3. Parede 2 — CAdES / A3 (`X-Signature`)

As operações de **exportação** pedem, por requisição, algo neste espírito:

> Base64 da assinatura **CAdES** de  
> `{"Timestamp":"...","RequestPath":"/api/exports/record-sets/{cpf}"}`

Assinar em CAdES exige a **chave privada**. Nesta serventia isso é o **certificado A3 do delegatário** (token).

Fato já medido nesta máquina (`ASSINATURA_DIGITAL_A3.md`):

- Carregar `eTPKCS11.dll` ou `IDPrimePKCS1164.dll` no processo → **segfault** (saída **139**)
- Segfault **mata o processo** — não é `try/except`
- Se o Flask/waitress do balcão carregasse o driver → **cai o sistema inteiro**, não só uma tela

Logo: **exportação automática “dentro” do processo do Cartório Gestão é impossível por construção**, enquanto a assinatura A3 não for feita **fora** desse processo (e a Cloudflare continuar fechada, a rede também impede o teste real).

---

## 4. O que o plano A3 resolve — e o que NÃO resolve

Plano (sandbox): `/workspace/sandbox-alteracoes/PLANO_A3_NOTAS_IMOVEIS.md`

### Já existe (padrão a reutilizar)

| Peça | Papel |
|---|---|
| `crc_a3.py` | Orquestra assinatura A3 em **subprocesso** — **nunca** carrega DLL no Flask |
| `crc_a3_assinador.py` | Processo filho: PKCS#11 / ctypes; PIN só em arquivo temp; sem PIN em log/banco/`.cred` |

Isso é o “caminho 2” que `ASSINATURA_DIGITAL_A3.md` previa: **assinatura fora do processo do balcão**.

### O plano A3 (Notas/Imóveis) pretende

1. Serviço local só em `127.0.0.1` (lista certs, assina PDF/XML/CAdES)  
2. Camada comum no CG (`assinar_com_a3` / similar) — módulos **não** falam com o token  
3. Auditoria sem PIN  
4. Mais tarde: montar `X-Signature` CAdES **se** houver caminho de rede que passe a Cloudflare

### Resolve (parede 2, no desenho)

- Isolar PKCS#11 para **não derrubar** o waitress  
- Assinar PDF de ensaio, e no futuro bytes CAdES para cabeçalhos  
- PIN na hora, nunca colado em chat

### NÃO resolve sozinho (parede 1)

- **Cloudflare 403** em cliente servidor  
- Pedido formal à CNB / allowlist  
- Credencial CCN “mágica” sem liberação de rede  
- Biometria oficial (continua no software/leitora reconhecidos pelo CNB)

**A3-3 no plano** (CCN + `X-Signature`) só faz sentido **depois** de um caminho que **passe** Cloudflare — allowlist ou fluxo navegador assistido. Sem isso, assinar CAdES localmente ainda não fala com a API.

---

## 5. Alternativas honestas (sem fingir transporte)

| Alternativa | O que é | Status |
|---|---|---|
| **1. Allowlist / API server-to-server (CNB-CF)** | Pedir por escrito: IP da serventia, host sem challenge, ou canal documentado para integração de cartório | **Caminho oficial preferido** para automação |
| **2. Fluxo navegador + A3 local** | Sessão humana já passa Cloudflare; o serviço A3 local só assina o payload / `X-Signature`; o envio usa a sessão do navegador (assistido) | **Honesto** se a central aceitar esse desenho; não é bypass |
| **3. Portal + upload manual** | Manter cadastros no Cartório Gestão; XML/importação pela **tela** do CCN; consulta no portal com certificado | **O que serve hoje** |
| **4. Aguardar orientação oficial** | CNB esclarece assinatura A3 + liberação de rede | Sem gambiarra |

Contatos já citados na documentação da casa / manual de chaves: **servicos@cnbcf.org.br**; artigos de suporte CCN no portal do notariado; WhatsApp suporte **(61) 3772-7800**.

Pedido típico ao CNB (três pontos):

1. Liberação servidor-a-servidor (anti-challenge) para o IP da serventia  
2. Orientação oficial para `X-Signature` CAdES com **A3** neste ambiente Windows  
3. Suporte à leitora biométrica (se for o caso), com marca/modelo e log

---

## 6. O que NÃO fazer

| Não fazer | Por quê |
|---|---|
| **Bypass / furar Cloudflare** (emular navegador só para burlar challenge, scrapers de challenge, etc.) | Ilegal / fora do contrato; a casa não implementa |
| Cliente CCN no sandbox que **finja** que a API responde | Tela mentirosa; regra da casa |
| Carregar PKCS#11 **dentro** do Flask do balcão | Segfault → queda do sistema |
| Colar `X-Api-Key` / AppToken / PIN em chat, ticket ou robô | Cofre = `/configuracoes` + `centrais_cred` / ProgramData — **quando** houver campo |
| Apontar sandbox `:8899` para produção CCN sem decisão do oficial | Homologação primeiro (`pessoas-hml`) |
| “Só falta colar a chave” | Faltam **rede** + **assinatura**; a chave é o terceiro passo |

---

## 7. Próximo passo concreto — ensaio A3-1 (PDF)

Antes de qualquer tentativa CCN:

1. **A3-1** no SERVIDOR sandbox: serviço local em `127.0.0.1` lista o certificado do token e **assina um PDF de teste** (“ensaio A3”).  
2. Cartório Gestão (`:8899`) só dispara via camada `assinar_com_a3` e registra auditoria (sem PIN).  
3. Token físico + PIN digitado na hora (nunca no chat).  
4. **Sem falar com CCN ainda.**

Detalhes, portas sugeridas e o que pedir ao oficial:  
`/workspace/sandbox-alteracoes/PLANO_A3_NOTAS_IMOVEIS.md` (marcos A3-0 … A3-5).

Referência de código já existente (CRC — mesmo padrão de isolamento):

- `SANDBOX\sistema\crc_a3.py`
- `SANDBOX\sistema\crc_a3_assinador.py`

---

## 8. Resumo em uma frase

**CCN automático está parado por Cloudflare (rede) e por CAdES/A3 (assinatura fora do Flask); o plano A3 ataca a segunda parede com isolamento tipo `crc_a3*`; a primeira só cai com allowlist CNB ou fluxo navegador assistido — sem bypass e sem cliente que finja transporte.**

---

*Documento criado em 2026-10-05 no sandbox. Não altera `notas_web` / `ri_web` / produção. Não reinicia `:8899`.*

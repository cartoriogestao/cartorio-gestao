# Serviço local A3 — sandbox (A3-0 / A3-1)

**Ofício Único de Cidade Exemplo/MA · Cartório Gestão**  
Porta aprovada pela Consultoria: **127.0.0.1:8766**  
Marco: listar certificados + assinar PDF de ensaio. **Sem** e-Notariado/CCN, **sem** selo automático, **sem** bypass Cloudflare.

## Tokens nesta casa (oficial, 05/10/2026)

Há **dois** tokens:

| Token | Middleware medido no SERVIDOR | DLL |
|---|---|---|
| **SafeID** | SafeSign IC Standard 3.5.3 (AETSign) | `aetpkss1.dll` (System32 e SysWOW64) |
| **A3** | SafeNet Authentication Client 10.6 / Gemalto IDGo 800 | `eTPKCS11.dll` / `IDPrimePKCS1164.dll` |

`WDPKCS*.dll` (Watchdata): **não encontrado** neste servidor.

A auto-detecção prefere, nesta ordem: `aetpkss1.dll` → `eTPKCS11.dll` → `IDPrimePKCS1164.dll` → …  
Override (se precisar do outro token): `--driver`, env `CG_A3_DRIVER` ou `a3_local.json`.

## O que é

Processo **à parte** do Flask (:8899) que:

1. Escuta **só** em `127.0.0.1:8766` (recusa `0.0.0.0`).
2. Auto-detecta o driver (lista acima) **sem carregar** a DLL no processo do serviço; PKCS#11 só no filho.
3. Em `GET /saude`, **lista os candidatos encontrados no disco** (`candidatos`).
4. Pede o **PIN só na hora** — nunca grava em `.cred`, banco, log ou argv.

O Cartório Gestão fala com ele só por `assinar_com_a3.py`.

## Como subir

No **SERVIDOR** de sandbox, pasta `SANDBOX\sistema`:

```bat
py -3 a3_servico_local.py
```

Forçar SafeID / SafeSign:

```bat
py -3 a3_servico_local.py --driver aetpkss1.dll
```

Ou:

```bat
set CG_A3_DRIVER=aetpkss1.dll
py -3 a3_servico_local.py
```

Ou arquivo `%PROGRAMDATA%\CartorioGestao\a3_local.json`:

```json
{"driver": "C:\\Windows\\System32\\aetpkss1.dll"}
```

Ensaio (outro terminal):

```bat
py -3 tools\a3_ensaio_cli.py saude
py -3 tools\a3_ensaio_cli.py certs
py -3 tools\a3_ensaio_cli.py assinar caminho\teste.pdf
```

O comando `assinar` pede o PIN no prompt (`getpass`) — **não** passe PIN na linha de comando.

## Rotas

| Método | Caminho | Função |
|---|---|---|
| GET | `/saude` | ok + driver + **candidatos** no disco |
| GET | `/certificados` | lista (pode estar vazia sem token) |
| POST | `/assinar/pdf` | JSON `{pdf_b64, pin, thumbprint?}` → CMS/assinatura |

## Camada no CG

```python
import assinar_com_a3 as A3
A3.status_do_servico()
A3.listar_certificados()
A3.assinar_pdf(pdf_bytes, pin, thumbprint=None)
```

## Ensaio na web (:8899)

`a3_ensaio_web.py` está pronto, **não** registrado em `app.py` neste marco (sem reinício). Use o CLI. Docstring do módulo explica como registrar no próximo start.

## Segurança

- Bind só localhost · PIN efêmero · logs sem body · sem CCN neste marco.

## Testes

```bat
py -3 -m pytest --noconftest tests\test_a3_servico_local.py -q
```

## O que falta para o oficial testar com token real

1. Conectar o token (SafeID ou A3) no SERVIDOR de sandbox.
2. Se o auto-detect pegar o driver do token “errado”, subir com `--driver` do desejado.
3. `py -3 a3_servico_local.py` no ar.
4. `tools\a3_ensaio_cli.py certs` e `assinar <pdf>` com PIN na hora.
5. Conferir o `.p7s` (CMS anexado).

**CCN:** fora deste marco. (Nota da Consultoria: acesso manual no navegador + assinatura na aba do usuário virá depois; sem cookies no servidor.)

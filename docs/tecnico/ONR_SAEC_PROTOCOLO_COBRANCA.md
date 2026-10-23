# ONR — SAEC, protocolo e cobrança (Marco B, sandbox)

> Só sandbox. Sem rede real / sem credencial real nos testes.
> UI (`ri_web`) bloqueada neste marco — foco em API + testes + esta nota.

## O que passou a estar ligado em `onr_api`

| Área | Caminhos ligados | Funções |
|---|---|---|
| SAEC | `atendimentos`, `atendimento`, `atendimento_interagir` | `atendimentos`, `atendimento`, `interagir_no_atendimento` |
| Protocolo | `protocolos`, `protocolo`, `protocolo_token_v2`, `protocolo_detalhes_v2`, `protocolo_token_validar_v2` | `protocolos`, `protocolo`, `token_do_protocolo`, `detalhes_do_protocolo`, `validar_token_do_protocolo` |
| Cobrança | `cobrancas`, `cobranca`, `cobranca_tipos_de_pagamento`, `cobranca_gerar` | `cobrancas`, `cobranca`, `tipos_de_pagamento`, `gerar_cobranca` |

Total: **25** de 53 em `CAMINHOS_LIGADOS` (antes 13).

## Fluxo do token do protocolo (segundo mecanismo)

1. `token_do_protocolo(numero, {"senha", "tipoSolicitacao"})` — Bearer da serventia.
2. `detalhes_do_protocolo(numero, token)` — cabeçalho `token: <token daquele protocolo>`.
3. `validar_token_do_protocolo(numero, token)` — mesma regra.

Mandar só o Bearer da casa nos detalhes costuma devolver 401.

## Como testar sem rede

```text
py -3 -m pytest --noconftest tests/test_onr_saec_protocolo_cobranca.py tests/test_onr_api.py -q
```

Os testes mockam `_bater` (e proíbem `_bater_cru`). Credencial continua em
`centrais_cred` / ProgramData — **não** há `.env` de secrets neste marco.

## Pendências (próximos pedaços)

- UI SAEC / protocolo na tela ONR (`ri_onr_web`) — depende de `ri_web` liberado.
- Cobrança: cancelar, devolução PIX, vincular protocolo (`cobranca_protocolo`), cadastrar.
- Protocolo: enviar/lote/download/excluir; detalhes v1 (fica só declarado).
- Filas legadas / caixa: amarrar cobrança ONR ao caixa local.
- Homologação real (com `.cred` de testes) — só com ok explícito do oficial.

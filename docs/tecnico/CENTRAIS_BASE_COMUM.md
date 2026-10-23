# Centrais — base comum das integrações (marco a)

Construído em 05/10/2026 no SANDBOX (3.6.285). **Não está em produção.**

## Quem é dono, quem consome

| Papel | Quem |
|---|---|
| **Dono** (cria, mantém, decide o contrato) | RCPN/Protesto |
| **Consome** | Notas e Registro de Imóveis — e depois migra `onr_api` / `cnib_api` para cá |

## As cinco peças

| Arquivo | O que faz | Fala com a rede? | Grava? |
|---|---|---|---|
| `centrais_http.py` | cliente HTTP comum: TLS 1.2+, prazo, retentativa básica, gancho mTLS | **sim** | não |
| `centrais_schema.py` | tabelas `centrais_fila` e `centrais_log` (`init_centrais_schema`, chamado em `database.init_schema`) | não | DDL |
| `centrais_fila.py` | fila genérica de envio/reprocesso | **não** (quem manda é o `enviar` do domínio) | sim |
| `centrais_log.py` | log estruturado por Central/operação, sanitizado | não | sim |
| `centrais_web.py` + `templates/centrais_status.html` | painel `/centrais/status` | não | só o «Reprocessar» (local) |

O cofre continua sendo **`centrais_cred.py`** — nada foi duplicado. O painel só
usa `centrais_cred.situacao()` (que nunca devolve segredo).

## Regras que a base carrega (e que todo consumidor herda)

1. **HTTPS obrigatório.** `http://` só para `127.0.0.1`/`localhost` com `permitir_http_local=True` (simuladores).
2. **TLS normal, sem certificado fixado**; não existe parâmetro para desligar a validação.
3. **Retentar só o que não chegou:** `GET/HEAD/OPTIONS` se retentam sozinhos (falha de transporte e 502/503/504); `POST/PUT/...` só com `retentar_escrita=True`.
4. **4xx/5xx não estoura** — volta `Resposta` com `status`; só falha de transporte levanta `CentralHttpError`.
5. **Rede nunca dentro de `db.transaction()`** — `centrais_http` não recebe `con`; `processar_proximo` pega o item, chama `enviar` sem transação aberta, anota depois.
6. **Produção só com permissão explícita** — `pegar_proximo`/`processar_proximo` deixam `PRODUCAO` de fora salvo `permitir_producao=True`.
7. **Payload por referência** (`payload_ref` = `tabela:id`/caminho), nunca o corpo com dado de gente.
8. **Log sem segredo e sem CPF/CNPJ** — chaves como `senha`, `token`, `authorization`, `x-api-key`, `client_secret` viram `«omitido»`; CPF/CNPJ ficam com só os 2 últimos dígitos; texto é cortado.
9. **Nada da serventia escrito no código** (CNS, CNPJ, nomes, IPs). `User-Agent` padrão é só `CartorioGestao`; quem quiser identificar a serventia passa `user_agent=` lido da configuração (`settings`). Há teste que varre os módulos novos.

## Contrato público

### `centrais_http`

```python
PRAZO_PADRAO = 30; TENTATIVAS_PADRAO = 2; ESPERA_BASE = 1.0
METODOS_QUE_SO_LEEM = {"GET","HEAD","OPTIONS"}; STATUS_TRANSITORIOS = {502,503,504}
USER_AGENT_PADRAO = "CartorioGestao"

class CentralHttpError(RuntimeError)        # falha de TRANSPORTE; .tentativas, .causa
@dataclass(frozen=True) class CertificadoCliente(arquivo_certificado, arquivo_chave=None, senha=None)
                                            # gancho mTLS (PEM/A1); senha fora do repr; A3 não
@dataclass(frozen=True) class Resposta(status, cabecalhos, corpo, texto, json, tentativas, duracao_ms, url, metodo)
    .ok -> bool                             # 2xx
    .como_dict() -> {"status","json","texto"}   # ADAPTADOR = formato dos `_bater` legados

def configuracao() -> dict                  # números do cliente p/ painel (sem segredo)
def contexto_tls(certificado=None, *, arquivo_ca=None) -> ssl.SSLContext
def requisitar(metodo, url, *, corpo=None, cabecalhos=None, json_corpo=None,
               prazo=PRAZO_PADRAO, tentativas=TENTATIVAS_PADRAO, retentar_escrita=False,
               certificado=None, contexto=None, permitir_http_local=False,
               user_agent=USER_AGENT_PADRAO) -> Resposta
```

### `centrais_fila`

Situações (`centrais_schema`): `PENDENTE`, `PROCESSANDO`, `ENVIADO` (recebido ≠ aceito), `CONFIRMADO`, `FALHOU`, `CANCELADO`.

```python
MAX_TENTATIVAS_PADRAO = 5; ESPERA_INICIAL_MIN = 1; ESPERA_MAXIMA_MIN = 60; MINUTOS_PARA_PRESO = 15
class FilaError(ValueError)                 # regra, frase de balcão
class FalhaDefinitiva(Exception)            # `enviar` levanta p/ não retentar (4xx de regra)

def enfileirar(con, central, operacao, payload_ref, *, ambiente="HOMOLOGACAO",
               chave=None, max_tentativas=5, por=None) -> int      # chave evita duplicata
def item(con, item_id) -> dict | None
def pegar_proximo(con, *, central=None, operacao=None,
                  ambientes=("HOMOLOGACAO","TESTES")) -> dict | None  # marca PROCESSANDO
def marcar_enviado(con, item_id, *, resposta_ref=None, status_http=None) -> None
def marcar_confirmado(con, item_id, *, resposta_ref=None) -> None
def marcar_falha(con, item_id, erro, *, definitiva=False, status_http=None) -> str  # PENDENTE c/ espera | FALHOU
def espera_da_tentativa(tentativas) -> int  # 1,2,4,8… min, teto 60
def devolver_presos(con, *, minutos=15) -> int
def reprocessar(con, item_id, *, por=None) -> dict   # LOCAL: FALHOU/CANCELADO -> PENDENTE
def cancelar(con, item_id, *, por=None, motivo="") -> None
def processar_proximo(db, enviar, *, central=None, operacao=None,
                      permitir_producao=False) -> dict | None
def resumo_por_central(con) -> list[dict]; def ultimas_falhas(con, *, central=None, limite=20) -> list[dict]
def listar(con, *, central=None, status=None, limite=100) -> list[dict]
```

Funções que recebem `con` **não fazem commit** — chame dentro de `db.transaction()`.

### `centrais_log`

```python
LOGGER = logging.getLogger("cartorio_gestao.centrais")   # linha JSON
def agora() -> str                          # ISO local, mesmo formato de database.ISO_DT
def sanitizar(valor) -> Any                 # cópia sem segredo e sem CPF/CNPJ
def mascarar_texto(texto, limite=500) -> str
def linha_estruturada(**campos) -> str
def registrar(con, central, operacao, evento, *, nivel="INFO", ambiente=None, fila_id=None,
              status_http=None, duracao_ms=None, mensagem="", detalhe=None) -> int
def registrar_resposta(con, central, operacao, resposta_ou_erro, *, ambiente=None, fila_id=None) -> int
def ultimos(con, *, central=None, operacao=None, nivel=None, limite=50) -> list[dict]
```

### `centrais_schema`

`init_centrais_schema(con)` — idempotente; tabelas `centrais_fila`, `centrais_log`. Sem migrações por enquanto (sem `PRAGMA`); a primeira coluna acrescentada entra no padrão de `ri_onr_central_schema` **e** o arquivo em `DONOS_DO_PRAGMA` de `tests/test_portabilidade.py`.

### Painel

- `GET /centrais/status[?central=CRA]` — ADMIN, MANAGER, AUDITOR. Resumo da fila por Central, últimas falhas, itens recentes, últimos erros do log, credenciais (só «informada»), números do cliente HTTP.
- `POST /centrais/status/<id>/reprocessar` — ADMIN, MANAGER, com CSRF, auditado (`CENTRAIS_REPROCESSO`). **Local**: devolve à fila, não envia nada.
- Link a partir de Configurações → seção Centrais.

## Como usar (exemplo para a etapa b)

```python
import centrais_cred as CRED, centrais_http as HTTP, centrais_fila as FILA, centrais_log as LOG

# 1) a rota que o operador clicou enfileira (referência, não corpo)
with db.transaction() as con:
    FILA.enfileirar(con, "CENPROT", "certidao_processar", f"cn_pendencias:{pid}",
                    ambiente=CRED.HOMOLOGACAO, chave=f"certidao:{pid}", por=usuario)

# 2) o processador chama a rede FORA da transação
def enviar(item):
    token = ...  # via centrais_cred (cofre) — nunca do código
    r = HTTP.requisitar("POST", base + "/v2/certidao/processar", json_corpo=montar(item),
                        cabecalhos={"Authorization": f"Bearer {token}"},
                        user_agent=f"CartorioGestao/{cns_lido_de_settings}")
    with db.transaction() as con:
        LOG.registrar_resposta(con, "CENPROT", item["operacao"], r, fila_id=item["id"])
    if 400 <= r.status < 500:
        raise FILA.FalhaDefinitiva(f"{r.status}: {r.texto[:200]}")
    if not r.ok:
        raise RuntimeError(f"{r.status}")
    return (r.json or {}).get("protocolo")

FILA.processar_proximo(db, enviar, central="CENPROT")   # produção só com permitir_producao=True

# 3) migrar um `_bater` legado sem mexer no resto: return HTTP.requisitar(...).como_dict()
```

## O que NÃO foi feito nesta etapa

- Nenhum `*_api.py` migrado; `cn_pendencias`/`pt_*`/`ri_onr_envios` continuam como estão.
- Nenhum processador agendado — `processar_proximo` só roda quando alguém o chamar (etapa b).
- Nenhum envio a Central (homologação ou produção).

# REGISTRO DE ALTERACOES DO SANDBOX

## 2026-10-05 — Trava de seguranca Centrais (prioridade teste cart)

**Motivo.** Antes do ensaio do cart no :8899, garantir que o sandbox NUNCA
bata em Central de producao (SIRC/Dataprev, CRC, ON-RCPN, Resolve, CENPROT/CRA
producao, e os 4 hosts de producao Notas/Imoveis).

**O que mudou (so SANDBOX/sistema/)**

- Novo centrais_trava_sandbox.py:
  - detecta sandbox por CARTORIO_GESTAO_SANDBOX=1 OU CARTORIO_GESTAO_DATA
    sob .../SANDBOX/...;
  - hosts com simulador (desvio obrigatorio): SIRC/CRC → :8917, ON-RCPN → :8915,
    Resolve → :8912, CENPROT → :8911, CRA producao → :8910;
  - deny-list inicial SEM simulador (recusa clara), alinhada Notas/Imoveis:
    pi.registrodeimoveis.org.br, serventia-api.onr.org.br,
    uth.id.onr.org.br, pessoas.e-notariado.org.br;
  - homolog liberada: 	estes-api.registrodeimoveis.org.br,
    pessoas-hml.e-notariado.org.br (e CRA homolog crama.cra21.com.br);
  - API estavel 
egistrar_host_producao(host, *, porta_simulador=None) para
    Notas registrar hosts extras sem fork;
  - proteger_url / destino_seguro / garantir_simulador.
- centrais_http.requisitar — gancho UNICO do transporte comum: chama
  TRAVA.proteger_url antes de abrir conexao (SIRC ja usa este caminho).
- crc_soap._bater, onrcpn_api.bater, 
esolve_api._bater — chamam
  TRAVA.destino_seguro (ainda nao migraram para centrais_http; mesma
  politica, sem logica duplicada).
- Testes: 	ests/test_centrais_trava_sandbox.py.
- Backup: ackups_patch/centrais_trava_sandbox_20261005/.

**Leitura (sem reiniciar :8899).** sirc_cliente.ENDERECO no codigo do
sandbox em disco continua https://sirc.dataprev.gov.br/SircWs/Movimento.
O processo :8899 sobe com sandbox_liga.instalar() (desvia para
127.0.0.1:8917 via tabela ENDERECOS). A trava nova esta em disco; o
processo :8899 so a carrega no proximo start (nao reiniciado nesta etapa).
Com a trava ativa: URL e forcada a https://127.0.0.1:8917/... ou recusa
clara se o simulador estiver fora — NUNCA cai na Dataprev.

**Nao tocado.** onr_api/cnib_api, produtividade*, notas_web, ri_web, :8899.

**Proximo.** Avisar Notas (API 
egistrar_host_producao) e teste cart;
depois retomar marco (d) ONRTDPJ.

## [2026-10-05 16:17] Notas/Imóveis — CCN fluxo acesso manual + envio na aba (esqueleto)

- Quem: Robô Integrações Notas e Imóveis (executor)
- Problema: oficial decidiu CCN = usuário entra manualmente no portal (Cloudflare + A3/SafeID) e o CG envia automaticamente **dentro da sessão do navegador**; faltava arquitetura + esqueleto de ensaio sem bypass e sem cliente Flask
- Solução: (1) documento de arquitetura em português (diagrama, papéis, sequência, browser vs servidor, riscos, homolog vs prod, dependência A3-1, pendências credencial/A3-3); (2) escolha **extensão MV3** (mais limpa que página auxiliar cross-origin); (3) pasta `ccn_assistente/` com README, contrato stub JSON `POST /assinar/cades`, extension (manifest só `pessoas-hml` + `127.0.0.1:8766`, content script com `credentials:include`, background chama A3 local). **Sem** cliente CCN no Flask; **sem** editar `notas_web`/`ri_web`/`atribuicoes_web`/modelos/produtividade; **sem** reiniciar :8899; **sem** produção
- Arquivos: `ccn_assistente/README.md`, `ccn_assistente/contrato/assinar_cades_ccn.stub.json`, `ccn_assistente/extensao/*` (manifest, background, content, popup), `docs/tecnico/CCN_FLUXO_ACESSO_MANUAL_ENVIO_ABA.md`. Box: `/workspace/sandbox-alteracoes/CCN_FLUXO_ACESSO_MANUAL_ENVIO_ABA.md` + cópia `ccn_assistente/`. Sem migração de banco; nenhum `.py` de balcão tocado
- Testes: N/A automatizado neste marco (esqueleto + doc). Validação: manifesto só homolog; content script guarda hostname; background trata 404 de `/assinar/cades` como pendente A3-3 (não finge sucesso)
- Risco para produção / como desfazer: zero em :8765 e :8899. Desfazer = apagar `ccn_assistente/` e o `.md` de documentação. Extensão só existe se carregada manualmente no Chrome em modo desenvolvedor
- Status: PRONTO NO SANDBOX (doc + esqueleto); pendente A3-3 CAdES real, credenciais CCN via UI, ensaio oficial com token + login homolog

---

# Checklist de melhorias — Cartório Gestão

Documento operacional para a equipe da serventia priorizar ajustes de **Visão geral** (painel `/`), **RTD** (atribuição **4**), **RCPJ** (atribuição **3**), **RCPN** (registro civil das pessoas naturais), **Malote**, **Livros e acervo**, **Tabelionato de Notas**, **Protesto** e **Registro de Imóveis (RI)**. **Gestão — Administrativo** e demais entradas do esqueleto ainda trazem só o menu até nova fatia do checklist.

| Campo | Valor |
|--------|--------|
| **Versão do sistema (referência)** | 3.6.193 (sandbox `:8899`, produção `:8765`) |
| **Rota canônica Visão geral** | `/` · `dashboard` (`@login_required`) |
| **Código principal Visão geral** | `app.py` (`dashboard`), `templates/dashboard.html`, `database.dashboard_stats`, `inacabados.resumo`, menu `base.html` (role-gating) |
| **Revisão base Visão geral** | [00-transversal](/cursor/stores/self/docs/revisao-modulos/00-transversal.md) · **TR-01** · achados T-02/T-03 · [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md) |
| **Rotas canônicas RCPJ/RTD** | `/rcpj-rtd` · discriminação `?atribuicao=3` (RCPJ) ou `4` (RTD) |
| **Rotas canônicas RCPN** | `/rcpn` · subfluxos `/rcpn/habilitacoes`, `/rcpn/proclamas`, `/rcpn/sirc`, `/rcpn/crc`, … |
| **Código principal RTD/RCPJ** | `rg_web.py` / `atribuicoes_web.py` (certidões, selagem RTDPJ) |
| **Código principal RCPN** | `atribuicoes_web.py`, `habilitacao_web.py`, `proclamas_web.py`, `papel_web.py`, `rc_pedidos_web.py`, `rc_modelos_livres_web.py` |
| **Revisão base RTD/RCPJ** | [06-rtd-rcpj](/cursor/stores/self/docs/revisao-modulos/06-rtd-rcpj.md) · matriz RT-01…RT-09 |
| **Revisão base RCPN** | [04-rcpn](/cursor/stores/self/docs/revisao-modulos/04-rcpn.md) · matriz RC-01…RC-31 · [MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md) |
| **Rotas Livros e acervo** | `/nucleo/livros` · `/nucleo/encerramento-diario` · `/nucleo/numeracao` · `/implantacao` · `/atribuicoes/importar` · `/importar-padrao` |
| **Código Livros e acervo** | `nucleo_web.py`, `escrituracao.py`, `livro_nucleo.py`, `implantacao.py`, `acervo_carga.py`, `importar_padrao.py`, `atribuicoes_web.py` |
| **Rotas canônicas Notas** | `/notas` · balcão, instrumentos, consulta, livros, remessas, modelos |
| **Código principal Notas** | `notas_web.py`, `notas_livro.py`, `notas_doi.py`, templates `notas_*` |
| **Revisão base Notas** | [03-notas](/cursor/stores/self/docs/revisao-modulos/03-notas.md) · **NT-01…NT-15** · [MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md) |
| **Rotas canônicas Protesto** | `/protesto` · CRA, CENPROT/Resolve, certidões, instrumentos |
| **Código principal Protesto** | `atribuicoes_web.py`, `cenprot_web.py`, CRA21/Resolve |
| **Revisão base Protesto** | [07-protesto](/cursor/stores/self/docs/revisao-modulos/07-protesto.md) · **PT-01…PT-16** |
| **Revisão base Livros/acervo** | [MATRIZ-COBERTURA](/cursor/stores/self/docs/revisao-modulos/MATRIZ-COBERTURA.md) · **OP-01…OP-07** · [05-ri](/cursor/stores/self/docs/revisao-modulos/05-ri.md) (matrícula importada) |
| **Rotas canônicas RI** | `/registro-imoveis` · `/ri/onr` · `/livro3` · `/usucapiao` · certidões L3 em `/atribuicoes/certidoes` |
| **Código principal RI** | `ri_web.py`, `ri_schema.py`, `ri_odt.py`, `ri_modelos_atos.py`, `ri_onr_web.py`, `onr_api.py`, `onr_endereco_web.py`, `cnib_web.py`, `usucapiao_web.py`, `retificacao_web.py`, `ra_*.py`, templates `ri_*`, `livro3_*`, `usucapiao_*` |
| **Revisão base RI** | [05-ri](/cursor/stores/self/docs/revisao-modulos/05-ri.md) · **RI-01…RI-21**, **L3-01…L3-04**, **US-01/02**, **RI-CNIB-01…03**, **RI-ONR-01…04** · [inventário ONR](/cursor/stores/self/docs/integracoes/inventario-onr-cartorio-gestao.md) · [livro3-ficha-formatacao](/cursor/stores/self/docs/livro3-ficha-formatacao.md) |
| **Atualizado em** | 2026-09-24 |

## Como usar

- Marque `- [x]` quando a melhoria estiver **implementada e conferida** no sandbox (e, se for o caso, em produção).
- Prioridade opcional: **P1** (risco operacional/legal ou bloqueio de fluxo) · **P2** (eficiência/qualidade) · **P3** (refino/cosmético).
- Itens **já entregues na 3.6.193** estão na seção [Concluído na 3.6.193](#concluído-na-36193); não duplicar trabalho salvo regressão.

## Referências legais e doutrinárias

- **Lei nº 6.015/73** — **Livro I** (registro civil das pessoas naturais: nascimento, casamento, óbito, Livro E, averbações); Livro III (RTD, arts. 127 e seguintes); Livro IV (RCPJ, arts. 136 e seguintes).
- **Lei nº 6.015/73 — Título V (Registro de Imóveis)** — livros do art. 173, matrícula, prioridade, prenotação, qualificação/dúvida, retificação (212–213), usucapião (216-A); **Código de Normas TJMA, Cap. III, arts. 424–773** (procedimento 436–545, certidões 546–559) — detalhes na seção [Registro de Imóveis (RI)](#registro-de-imóveis-ri).
- **Normas CNJ/TJMA** — tabela de emolumentos/selos (RTDPJ, RCPN), CRC/SIRC/FUNAI/IBGE, integração ONRTDPJ/ONRCPN quando aplicável.
- **Alberto Gentil, *Registros Públicos*** — RCPN: assentos, publicidade, qualificação e retificação; RTD: natureza do registro de títulos, qualificação e recusa; RCPJ: atos de pessoas jurídicas e publicidade registral. *(PDF «Registros Públicos (Alberto Gentil)» não localizado neste ambiente; conferir capítulos do Livro I/III/IV na edição da serventia antes de citar página.)*

## Legenda de categorias

| Categoria | O que registrar aqui |
|-----------|----------------------|
| **Apresentação/UI** | Layout, rótulos, título de aba, navegação, mensagens |
| **Funcionalidade** | Lacunas, bugs, integrações (ONRTDPJ, selador, caixa) |
| **Eficiência** | Cliques, defaults, atalhos, lote, validação antecipada |
| **Adequação legal/doutrinária** | Lei 6.015/73, CNJ/TJMA, Gentil |

---

## Concluído na 3.6.193

Itens verificados na revisão modular; **não** reabrir salvo regressão.

- [x] **Menu O5 RCPJ/RTD** — fases A/B/C de listagem e rotas agregadas **ABC** (RT-01…RT-09, exceto certidão IT bloqueada por seed).
- [x] **Prévia de teor RCPJ** — registro seed **#1**, rotas `/rcpj-rtd/1/teor/previa` e `teor-averbacao/previa` (**RG-03**, amostra Auto=Y).
- [x] **Transversal 3.6.193** — melhorias de título de aba em outros módulos (Notas, caixa, protocolo); **sem** mudança funcional específica RTD/RCPJ no release note.
- [x] **Menu O3 RCPN** — 31 entradas de menu **ABC** (RC-01…RC-31; [04-rcpn](/cursor/stores/self/docs/revisao-modulos/04-rcpn.md)).
- [x] **Termo nascimento ODT** — `/rcpn/assentos/1/termo.odt` amostra Auto=Y (**RX-05** / **PA-RC_TERMO_NASCIMENTO**).
- [x] **Certidão nascimento ensaio** — molde #1 ODT/PDF (`semear.py --ensaio-revisao`, **MO-RC-N**); selo sandbox **RC-03**.
- [x] **Notas — títulos de aba** por família de instrumentos (**N-01**, 3.6.187/193).
- [x] **Notas — reconhecimento** explicação semelhança/autenticidade recolhível na tela.
- [x] **Notas — DOI partes** na ficha do ato (alienante/adquirente, `notas_doi`).
- [x] **Notas — selo arquivamento 16.39** opcional na lavratura + `POST /notas/atos/<id>/selar-arquivamento` (3.6.192).
- [x] **Notas — depósito na lavratura** — mesmo depósito do caixa, baixa na ficha (3.6.192).
- [x] **Notas — folhas até 2v** no lançamento do livro quando o texto ocupa verso (3.6.192).
- [x] **Notas — título escritura** único no cabeçalho da família (`notas_familia.html`, 3.6.192).
- [x] **Protesto — redirect** `/protesto/titulos` → `/protesto` (**PR-01**, 3.6.188).

*Registro de Imóveis: itens já entregues estão em [RI — Concluído na 3.6.193](#ri--concluído-na-36193-não-reabrir-salvo-regressão).*

---

# RTD — Registro de Títulos e Documentos (atribuição 4)

## RTD — Títulos apresentados (`/rcpj-rtd/titulos?atribuicao=4`)

**Apresentação/UI**

- [ ] **P1** Corrigir **título da aba/janela** quando `atribuicao=4`: hoje aparecem **ambos** os rótulos «RTD — títulos apresentados · RCPJ — títulos apresentados» (**RG-01**; evidência [revisao-smoke-rtd-selo-protesto.json](/cursor/stores/self/internal/revisao-modulos/revisao-smoke-rtd-selo-protesto.json)).
- [ ] **P2** Destacar visualmente a **atribuição ativa** (faixa ou subtítulo «RTD — atribuição 4») na lista e na ficha do título.
- [ ] **P3** Links «Acessos relacionados» da lista de registros lavrados misturam atalhos de **RCPN/RI/Protesto** (ruído no manual gerado) — filtrar por contexto RTD.

**Funcionalidade**

- [ ] **P2** Garantir que filtros e paginação **preservem** `atribuicao=4` em todos os `url_for` (evitar título RTD aparecer na fila RCPJ).
- [ ] **P2** Indicador de **origem ONRTDPJ** na fila (protocolo central, situação) sem abrir a ficha.

**Eficiência**

- [ ] **P2** Atalho «+ Receber título» com **livro/série RTD** pré-selecionado conforme último uso ou configuração da casa.
- [ ] **P3** Colunas configuráveis (data apresentação, natureza, situação, prazo exigência).

**Adequação legal/doutrinária**

- [ ] **P1** Checklist na recepção: **natureza do título** compatível com RTD (Lei 6.015/73, Liv. III; Gentil — títulos registráveis vs recusa fundada).
- [ ] **P2** Campo «vias»/«forma de apresentação» alinhado ao que a serventia exige para contagem de atos/custas.

## RTD — Receber título (`/rcpj-rtd/titulos/novo?atribuicao=4`)

**Apresentação/UI**

- [ ] **P2** Título da tela «Receber título — **RTD**» (não genérico RCPJ/RTD).
- [ ] **P3** Agrupar campos: apresentante · documento · natureza · livro pretendido.

**Funcionalidade**

- [ ] **P2** Validar **CPF/CNPJ** do apresentante antes de protocolar (mensagem clara, não erro genérico).
- [ ] **P2** Bloquear série/livro **RCPJ** quando `atribuicao=4`.

**Eficiência**

- [ ] **P2** Default **data/hora** de apresentação = agora (editável).
- [ ] **P2** Reutilizar último apresentante frequente (autocomplete).

**Adequação legal/doutrinária**

- [ ] **P1** Registrar **data da apresentação** como marco para prazos de qualificação/exigência (Lei 6.015/73; prática Gentil — qualificação registral).

## RTD — Ficha do título apresentado (`/rcpj-rtd/titulo/<id>`)

**Apresentação/UI**

- [ ] **P2** Separar abas ou seções: **Apresentação** · **Qualificação** · **Exigências/negativa** · **Registro** · **Central ONRTDPJ** · **Anexos**.
- [ ] **P2** Botões de ação com ordem sugerida (qualificar → exigir → lavrar → informar central).

**Funcionalidade**

- [ ] **P1** Fluxo **negativa qualificada**: exigências, fundamento, prazo — conferir impressão/PDF da nota devolutiva e vínculo com ONRTDPJ.
- [ ] **P1** **Lavrar o registro** a partir do título só após qualificação positiva; mensagem se tentar pular etapa.
- [ ] **P2** Anexo obrigatório do título: preview inline (PDF/imagem) na ficha.
- [ ] **P2** Ações ONRTDPJ (orçamento, registro, cancelamento, nota) com **log de retorno** visível ao operador.

**Eficiência**

- [ ] **P2** «Prévia do teor (PDF)» antes de lavrar, com mesma série RTD do título.
- [ ] **P2** Encaminhamento/encerramento com **motivo mínimo** (10 letras) — validar antes do submit, não só no servidor.

**Adequação legal/doutrinária**

- [ ] **P1** Qualificação **NEGATIVA** vs registro: uso correto do termo (PROBLEMA_75 — «NEGATIVA» legítima em `rg_titulo`; não confundir com certidão negativa de RI).
- [ ] **P2** Fundamentação da recusa citável (artigo/norma interna) no teor da exigência.

## RTD — Registros lavrados (`/rcpj-rtd?atribuicao=4`)

**Apresentação/UI**

- [ ] **P2** Título da página: «RTD — registro de títulos e documentos» (smoke OK em `?atribuicao=4`; manter paridade com RCPJ).
- [ ] **P3** Ocultar coluna «Atribuição» quando filtro fixo RTD.

**Funcionalidade**

- [ ] **P2** Busca por **número do registro**, requerente, natureza, selo.
- [ ] **P2** Situação (aberto, encerrado, cancelado) consistente com livro físico.

**Eficiência**

- [ ] **P2** Atalho «+ Registro novo» com `atribuicao=4` e séries RTD.

**Adequação legal/doutrinária**

- [ ] **P2** Conferência livro/folha vs numeração eletrônica antes de selar (Gentil — sequência e publicidade).

## RTD — Novo registro direto (`/rcpj-rtd/novo?atribuicao=4`)

**Apresentação/UI**

- [ ] **P2** Aviso quando registro direto **dispensa** título apresentado — risco de pular qualificação.

**Funcionalidade**

- [ ] **P1** Série/livro **obrigatório** coerente com RTD; selo opcional não grava sigla RCPJ (**código** já distingue `RG.SERIES_RCPJ`).
- [ ] **P2** POST sandbox/regressão: erro fatal zero (passagem 2d registrada na revisão).

**Eficiência**

- [ ] **P3** Teor opcional na abertura — permitir lavrar depois na ficha.

**Adequação legal/doutrinária**

- [ ] **P1** Registro direto apenas para hipóteses admitidas na casa (ato já qualificado fora do fluxo título) — documentar na ajuda.

## RTD — Ficha do registro (`/rcpj-rtd/<registro_id>`)

**Apresentação/UI**

- [ ] **P2** Rótulo **Requerente** (não «parte» genérica) — alinhado ao manual operacional.
- [ ] **P2** Lista de atos posteriores com tipo, data, selo, link para teor.

**Funcionalidade**

- [ ] **P1** **Selagem no ato** RTD: item TJ correto, sigla **RTD** no envelope RTDPJ; pós-selo redirecionar para **etiqueta** quando aplicável (`_destino_apos_selar_rtdpj`).
- [ ] **P2** Anexar imagem/PDF do **livro** (`/arquivo`) com pasta `RCPJ/<serie>/` — conferir nomenclatura «RCPJ» na pasta vs atribuição RTD (confusão operacional).
- [ ] **P2** Corrigir requerente com **motivo** obrigatório (auditoria).
- [ ] **P2** Certidões na ficha: emitir inteiro teor com seleção de atos posteriores.

**Eficiência**

- [ ] **P2** «Últimos atos» linkado filtrado por este registro.
- [ ] **P2** Prévia teor averbação/registro sem gravar ato (`/teor/previa`, `/teor-averbacao/previa`).

**Adequação legal/doutrinária**

- [ ] **P1** Cada averbação em **folha nova** (regra RCPJ/RTD no código) — UI deve deixar explícito ao lançar.
- [ ] **P2** Arquivamento **15.22** quando cobrado no protocolo — prévia de averbação consulta item no protocolo.

## RTD — Teor do ato (`/rcpj-rtd/ato/<ato_id>/teor`)

**Apresentação/UI**

- [ ] **P2** Indicar se ato é **registro** ou **averbação** no cabeçalho.

**Funcionalidade**

- [ ] **P2** Modelos `RTD_TEOR_*` / chaves em `rg_teor_rtdpj` — amostra RTD ainda **AB** ([MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md)).
- [ ] **P2** Export ODT/PDF do teor lavrado comparável ao selado (checklist humano slots 17–19).

**Eficiência**

- [ ] **P3** Editor com marcadores da casa (mesmo padrão Notas/RI).

**Adequação legal/doutrinária**

- [ ] **P1** Teor deve reproduzir **elementos essenciais** do título registrado (Gentil — princípio da especialidade/publicidade).

## RTD — Certidão de inteiro teor (compartilhada `/atribuicoes/certidoes`)

**Apresentação/UI**

- [ ] **P1** Título da página repetir filtro ativo: «Certidões — **RTD**» quando `atribuicao=4` ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).
- [ ] **P2** Separar visualmente RTD · RCPJ · Livro 3 na mesma tela.

**Funcionalidade**

- [ ] **P1** **Seed sandbox** sem certidões RTD (`at_certidoes=0`) — impede fase C (**RG-02**, **BLOCKED**); incluir amostra mínima RI-08/21 + RTD/RCPJ.
- [ ] **P2** Prévia certidão (`/rcpj-rtd/<id>/certidao/previa`) — capa/faixa **AB**; validar visual vs PDF selado.
- [ ] **P1** Selagem certidão via `_selar_a_certidao_rtdpj` — itens do protocolo, caminho genérico RTDPJ.
- [ ] **P2** Cancelamento certidão: selo cancelado TJMA + motivo (paridade protesto/RCPN).

**Eficiência**

- [ ] **P2** Emitir a partir da ficha do registro com atos posteriores **pré-marcados** conforme pedido do cliente.

**Adequação legal/doutrinária**

- [ ] **P1** Inteiro teor = registro principal + atos posteriores selecionados ([MANUAL_OPERACIONAL_DO_SISTEMA.md](MANUAL_OPERACIONAL_DO_SISTEMA.md) — não omitir averbação/cancelamento).
- [ ] **P2** Certidão negativa de qualificação ≠ certidão de inteiro teor (Gentil / Lei 6.015).

---

# RCPJ — Registro Civil das Pessoas Jurídicas (atribuição 3)

## RCPJ — Títulos apresentados (`/rcpj-rtd/titulos?atribuicao=3`)

**Apresentação/UI**

- [ ] **P1** Corrigir **título da aba** para `atribuicao=3`: hoje duplica RTD+RCPJ no título (**RG-01**).
- [ ] **P2** Destaque «RCPJ — atribuição 3» na lista.

**Funcionalidade**

- [ ] **P2** Preservar `atribuicao=3` em toda navegação da fila.
- [ ] **P2** Indicador ONRTDPJ na fila (pedidos de registro de PJ via central).

**Eficiência**

- [ ] **P2** «+ Receber título» com séries **RCPJ** default.

**Adequação legal/doutrinária**

- [ ] **P1** Natureza do documento = ato constitutivo/alteração/dissolução etc. (Lei 6.015/73, Liv. IV; Gentil — PJ).
- [ ] **P2** Conferir **tipo de pessoa jurídica** vs livro/série interna da serventia.

## RCPJ — Receber título (`/rcpj-rtd/titulos/novo?atribuicao=3`)

**Apresentação/UI**

- [ ] **P2** Título «Receber título — **RCPJ**».

**Funcionalidade**

- [ ] **P2** Impedir livro **RTD** quando `atribuicao=3`.
- [ ] **P2** Validação documento apresentante (CNPJ frequente).

**Eficiência**

- [ ] **P2** Defaults de natureza («Contrato social», «Alteração», «Ata») configuráveis.

**Adequação legal/doutrinária**

- [ ] **P1** Exigir indicação do **ato** que se pretende registrar (constituição, filial, etc.).

## RCPJ — Ficha do título apresentado (`/rcpj-rtd/titulo/<id>`)

**Apresentação/UI**

- [ ] **P2** Mesma organização em seções que RTD; linguagem PJ (sócio/administrador, CNPJ, sede).

**Funcionalidade**

- [ ] **P1** Qualificação de **ato de PJ** — integração ONRTDPJ (orçamento, registro informado, cancelamento).
- [ ] **P2** Lavrar registro com **teor** adequado a PJ (modelos RCPJ).
- [ ] **P2** Nota devolutiva à Central — impressão e arquivo.

**Eficiência**

- [ ] **P2** Prévia PDF do registro antes de lavrar (amostra OK no seed #1 para RCPJ — manter RTD).

**Adequação legal/doutrinária**

- [ ] **P1** Recusa fundada quando falta requisito legal de registro de PJ (Lei 6.015/73; Gentil — documentação constitutiva).
- [ ] **P2** Publicidade: dados essenciais da PJ no teor registrado.

## RCPJ — Registros lavrados (`/rcpj-rtd?atribuicao=3`)

**Apresentação/UI**

- [ ] **P2** Título «RCPJ — registro civil das pessoas jurídicas» (smoke: título OK em `?atribuicao=3`).

**Funcionalidade**

- [ ] **P2** Busca por **CNPJ**, razão social, número registro.

**Eficiência**

- [ ] **P2** Filtro situação + paginação estável.

**Adequação legal/doutrinária**

- [ ] **P2** Histórico de alterações contratuais encadeado na ficha (atos posteriores).

## RCPJ — Novo registro direto e ficha (`/rcpj-rtd/novo`, `/rcpj-rtd/<id>`)

**Apresentação/UI**

- [ ] **P2** Identificação clara **PJ** no formulário (razão, CNPJ, sede).

**Funcionalidade**

- [ ] **P1** Sigla **RCPJ** no selo do ato (não RTD) — regressão conhecida corrigida no código; manter teste.
- [ ] **P2** Certidão de **ata** vs certidão de registro — não confundir espécies (PROBLEMA_75).

**Eficiência**

- [ ] **P2** Prévia teor registro/averbação (**RG-03** amostra OK — estender validação a mais registros).

**Adequação legal/doutrinária**

- [ ] **P1** Averbação de alteração sem substituir registro originário (cadeia registrária).

## RCPJ — Teor e certidões

**Funcionalidade**

- [ ] **P2** Modelos `RCPJ_TEOR_REGISTRO` / `RCPJ_TEOR_AVERBACAO` — amostra Auto=Y; certidão ODT ainda **AB** por seed.
- [ ] **P2** Prévia certidão capa/faixa RCPJ — exercício pendente (MODELOS-EMISSAO).

**Adequação legal/doutrinária**

- [ ] **P1** Certidão reproduz inteiro teor do registro PJ + averbações selecionadas.

---

# Transversal RCPJ / RTD

## Últimos atos praticados (`/rcpj-rtd/atos`)

**Apresentação/UI**

- [ ] **P2** Filtro default «hoje» ou «últimos 7 dias».

**Funcionalidade**

- [ ] **P2** Filtro atribuição + tipo de ato funcional (registro/averbação/certidão).

**Eficiência**

- [ ] **P2** Link direto para ficha do registro e para etiqueta.

**Adequação legal/doutrinária**

- [ ] **P3** Conferência diária cruzada com encerramento/livro físico.

## Etiquetas de selos externos (`/rcpj-rtd/etiquetas/selos-externos`)

**Apresentação/UI**

- [ ] **P2** Instrução visível: só selo **realmente obtido fora** do fluxo normal.

**Funcionalidade**

- [ ] **P1** Validação número selo + texto registro/averbação antes de imprimir lote.
- [ ] **P2** Busca por parte/ato/selo — performance em acervo grande.

**Eficiência**

- [ ] **P2** Marcar todos / imprimir selecionados — conferir contagem.

**Adequação legal/doutrinária**

- [ ] **P1** Etiqueta deve permitir **rastreio** ao ato (QR/configuração em ajuste).

## Ajustar etiqueta de registro (`/rcpj-rtd/etiqueta/ajuste`)

**Apresentação/UI**

- [ ] **P3** Prévia ao vivo da etiqueta 90×40 mm.

**Funcionalidade**

- [ ] **P2** Persistência por serventia (mm, QR, fonte).

**Eficiência**

- [ ] **P3** Perfil de impressora (deslocamento x/y) nomeado.

**Adequação legal/doutrinária**

- [ ] **P2** Conteúdo mínimo exigido pelo TJMA no QR/texto.

## Etiqueta pós-selo (`/rcpj-rtd/ato/<ato_id>/etiqueta`)

**Funcionalidade**

- [ ] **P2** Impressão imediata após selagem bem-sucedida (fluxo `_destino_apos_selar_rtdpj`).

**Eficiência**

- [ ] **P3** Link «Ajustar etiqueta» acessível na mesma tela.

## Central ONRTDPJ (`/rcpj-rtd/onrtdpj`)

**Apresentação/UI**

- [ ] **P2** Estado da credencial (PRODUCAO informada — [PEDIDO_DAS_CREDENCIAIS.md](PEDIDO_DAS_CREDENCIAIS.md)) visível na tela.

**Funcionalidade**

- [ ] **P1** «Testar a ligação» + «Trazer» — tratar erro de API com mensagem acionável.
- [ ] **P1** Sincronizar situação título local ↔ central (nota, orçamento, registro, cancelamento) sem duplicar protocolo.
- [ ] **P2** Role-gated: apenas perfis autorizados trazem fila.

**Eficiência**

- [ ] **P2** Abrir título local a partir da linha da fila central.

**Adequação legal/doutrinária**

- [ ] **P2** Prazos e respostas à central documentados no teor/nota devolutiva.

## Modelos dos documentos (`/rcpj-rtd/modelos`)

**Apresentação/UI**

- [ ] **P2** Listar chaves RCPJ vs RTD separadas (certidão, teor registro, teor averbação, nota).

**Funcionalidade**

- [ ] **P2** Prévia modelo (`/modelos/previa`) — matriz **ABCM** RT-09.
- [ ] **P2** Herdar vs «Salvar para todos» — governança de mudança.

**Eficiência**

- [ ] **P3** Diff contra molde padrão antes de salvar.

**Adequação legal/doutrinária**

- [ ] **P1** Modelos de certidão/teor compatíveis com Lei 6.015 e prática Gentil (sem cláusulas que alterem o registro).

## Selagem e caixa (RTDPJ)

**Funcionalidade**

- [ ] **P1** Caminho selador RTDPJ genérico + itens tabela emolumentos (**grupo 15** RTD/PJ vs confusão Livro 3 — [FILA_DO_LIVRO_3.md](FILA_DO_LIVRO_3.md)).
- [ ] **P2** Depósito prévio **tipo serviço 23** (RCPJ **e** RTD) — [O_TIPO_DE_SERVICO_DO_DEPOSITO](/cursor/stores/self/docs/tecnico/O_TIPO_DE_SERVICO_DO_DEPOSITO.md).
- [ ] **P2** Lista **Selos emitidos** (`/selos`) filtrável por atribuição RTD/RCPJ.

**Eficiência**

- [ ] **P2** Protocolo geral vinculado ao título/registro sem re-digitar custas.

**Adequação legal/doutrinária**

- [ ] **P1** Não emitir selo sem ato lavrado; recuperação de selo solto sem duplicar ato ([MANUAL_OPERACIONAL_DO_SISTEMA.md](MANUAL_OPERACIONAL_DO_SISTEMA.md) — problemas frequentes).

## URLs e suporte remoto

**Apresentação/UI**

- [ ] **P2** URLs amigáveis ou breadcrumb fixo: `/rcpj-rtd/titulos?atribuicao=4` difícil de ditar — considerar alias `/rtd/titulos` ([critica-telas](/cursor/stores/self/docs/critica-telas-sandbox.md)).

**Eficiência**

- [ ] **P3** Copiar link «deep link» com atribuição da ficha atual.

---

# RCPN — Registro Civil das Pessoas Naturais (Livro I)

Módulo **Atribuições → Registro Civil das Pessoas Naturais**. Rotas sob `/rcpn/*`; código em `atribuicoes_web.py`, `habilitacao_web.py`, `proclamas_web.py`, `papel_web.py`, `rc_pedidos_web.py`, `rc_modelos_livres_web.py`. Revisão sandbox **O3** — [04-rcpn](/cursor/stores/self/docs/revisao-modulos/04-rcpn.md), matriz **RC-01…RC-31** ([MATRIZ-COBERTURA](/cursor/stores/self/docs/revisao-modulos/MATRIZ-COBERTURA.md)).

**Base legal/doutrinária (RCPN):** Lei **6.015/73**, **Livro I** (nascimento, casamento, óbito, Livro E, averbações); CNJ/TJMA (selos, tabelas, CRC/SIRC); **Alberto Gentil** — registro civil, publicidade e qualificação dos assentos *(PDF «Registros Públicos» / capítulos de registro civil não localizado neste ambiente — conferir edição da serventia.)*.

---

## RCPN — Assentos (`/rcpn`)

**Apresentação/UI**

- [x] **P3** Título de aba coerente «Registro Civil — assentos» (**RC-N01**, smoke O3).
- [ ] **P1** Reduzir ruído visual: blocos «Importar» + «Digitar» + atalhos + tabela na mesma dobra — orientar **novo nascimento** vs **consulta** ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).
- [ ] **P2** Cabeçalho cartorial repetido ocupa ~25% da viewport — recolher ou omitir em telas operacionais.
- [ ] **P2** Filtros por espécie (N/C/O/Livro E), livro, folha, nome do registrado — preservar na paginação.

**Funcionalidade**

- [ ] **P1** Busca por nome, matrícula, CPF, livro/folha — tolerante a acento e nome parcial.
- [ ] **P2** Indicador visual de assento **rascunho** vs **lavrado** vs **cancelado**.
- [ ] **P2** Atalhos «Nascimento» / «Casamento» / «Óbito» abrem espécie correta em `/rcpn/novo/<especie>`.

**Eficiência**

- [ ] **P2** Últimos assentos lavrados pelo operador (atalho na lista).
- [ ] **P3** Colunas configuráveis (data registro, espécie, selo).

**Adequação legal/doutrinária**

- [ ] **P1** Não permitir lavrar sem campos mínimos do assento exigidos pelo Livro I / normas CNJ (checklist pré-lavratura).

## RCPN — Ficha do assento (`/rcpn/assentos/<id>`)

**Apresentação/UI**

- [ ] **P2** Seções claras: **Dados do assento** · **Pessoas** · **Atos/Averbações** · **Termo** · **Certidões** · **Comunicações** · **Selos**.
- [ ] **P2** Espécie (nascimento/casamento/óbito/Livro E) visível no cabeçalho.

**Funcionalidade**

- [ ] **P1** «Lavrar» / «Lançar» só após conferência (`rcpn_conferencia`) — bloquear duplo lançamento.
- [ ] **P1** Vínculo matrícula única nacional — alertar colisão ou formato inválido antes de selar.
- [ ] **P2** Histórico de importação/acervo vs digitação manual auditável.
- [ ] **P2** Anexos (documentos hospitalares, mandados, procurações) com preview.

**Eficiência**

- [ ] **P2** Atalhos: averbar · retificar · anotar · termo · emitir certidão · comunicação pendente.
- [ ] **P2** «Confirmar livro/folha» (`rcpn_confirmar_livro`) com validação de sequência.

**Adequação legal/doutrinária**

- [ ] **P1** Retificação/suprimento via fluxo próprio — não sobrescrever termo lavrado sem averbação/retificação (Gentil — segurança jurídica).
- [ ] **P2** Filiação e nomes conforme regras de registro (inclusive retificação de patronímico).

## RCPN — Novo assento e escolha de espécie (`/rcpn/novo`, `/rcpn/novo/<especie>`)

**Apresentação/UI**

- [ ] **P2** Wizard ou passos numerados: espécie → formulário → conferência → lavratura.
- [ ] **P2** Rascunho automático (`rcpn_assento_novo`) — indicador «continuar rascunho».

**Funcionalidade**

- [ ] **P1** Impedir misturar espécie errada (ex.: campos de óbito em nascimento).
- [ ] **P2** Integração declaração de nascido vivo / documento médico quando aplicável.
- [ ] **P2** Casamento: exigir habilitação expedida ou exceção legal documentada.

**Eficiência**

- [ ] **P2** Defaults de livro/folha conforme espécie e numeração da serventia.
- [ ] **P3** Duplicar assento gêmeo a partir do irmão (`/rcpn/gemeos`).

**Adequação legal/doutrinária**

- [ ] **P1** Prazos legais (registro tardio, natimorto, etc.) — aviso quando data do fato exige procedimento específico.

## RCPN — Conferência e lavratura (`rcpn_conferencia`, `rcpn_lancar`)

**Funcionalidade**

- [ ] **P1** Conferência side-by-side: formulário vs minuta do termo antes do selo.
- [ ] **P1** Falha do selador não deve marcar assento como lavrado (paridade teste habilitação).
- [ ] **P2** Gratuidade / isenção (`g.rcpn_gratuidade_override`) — motivo obrigatório e trilha de auditoria.

**Eficiência**

- [ ] **P2** Voltar à ficha com mensagem clara após lavratura bem-sucedida.

**Adequação legal/doutrinária**

- [ ] **P1** Emolumento/selo coerente com espécie e tabela TJMA antes de concluir.

## RCPN — Teores por formulário (`/rcpn/formulario/<chave>`)

**Apresentação/UI**

- [ ] **P2** Título indica espécie e etapa (ex.: «Teor — nascimento — filiação»).

**Funcionalidade**

- [ ] **P1** Campos obrigatórios CNJ/CRC refletidos no formulário dinâmico.
- [ ] **P2** Validação cruzada (datas, idade, estado civil) com mensagens em português claro.

**Eficiência**

- [ ] **P2** Salvar parcial sem perder navegação entre subformulários.

**Adequação legal/doutrinária**

- [ ] **P1** Dados exportáveis ao SIRC/CRC/IBGE consistentes com o formulário (mesma semântica de campos).

## RCPN — Termo do assento (`/rcpn/assentos/<id>/termo`, ODT/PDF)

**Apresentação/UI**

- [ ] **P2** Estado «termo escrito» vs «pendente» visível na ficha e em `/rcpn/termos-a-escrever`.

**Funcionalidade**

- [x] **P2** Export **ODT** termo nascimento seed `#1` — amostra OK (`GET /rcpn/assentos/1/termo.odt`, **RX-05**, **PA-RC_TERMO_NASCIMENTO**).
- [ ] **P2** Termos casamento/óbito/Livro E — amostras **AB** ([MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md)).
- [ ] **P2** Escrita livre + modelos `rc_modelos_do_livro` — sincronizar marcadores `@` com ficha.
- [ ] **P2** PDF do termo (`rcpn_termo_pdf`) — paridade visual com ODT selado.

**Eficiência**

- [ ] **P2** Abrir ODT no LibreOffice local sem passo extra oculto.

**Adequação legal/doutrinária**

- [ ] **P1** Termo lavrado contém elementos essenciais do assento (Lei 6.015/73 Liv. I; Gentil — publicidade).

## RCPN — Checklist do assento (`/rcpn/assentos/<id>/checklist`)

**Funcionalidade**

- [ ] **P1** Itens de checklist alinhados às exigências da serventia/CNJ — bloquear selo se P1 pendente.
- [ ] **P2** Lista `/rcpn/checklist-pendente` agregada — link direto para resolver na ficha.

**Adequação legal/doutrinária**

- [ ] **P2** Documentar na ajuda quais itens são legais vs house policy.

## RCPN — Averbações (`/rcpn/averbacoes`)

**Apresentação/UI**

- [ ] **P2** Filtro por espécie, data, tipo de averbação, operador.

**Funcionalidade**

- [ ] **P1** Lançamento averbação (`rcpn_averbar`) — selagem e etiqueta (`rcpn_ato_etiqueta`, ajuste `/rcpn/etiqueta/averbacao/ajuste`).
- [ ] **P2** Averbação de CPF (`rcpn_averbar_cpf`) integrada à fila `/rcpn/cpf` e `/rcpn/dados-cadastrais`.
- [ ] **P2** Anotação vs averbação vs retificação — rótulos distintos na UI.

**Eficiência**

- [ ] **P2** Abrir assento origem a partir da linha.

**Adequação legal/doutrinária**

- [ ] **P1** Averbação não altera o termo originário — novo ato encadeado (Gentil).

## RCPN — Retificação e suprimento (`/rcpn/retificacoes`, processo)

**Funcionalidade**

- [ ] **P1** Fluxo retificação (`rcpn_retificacao_nova`, `rcpn_retificacao`) — mandado/anuência anexos.
- [ ] **P1** Suprimento vs retificação — espécies corretas no protocolo e selo.
- [ ] **P2** Status do processo (aberto, concluído, aguardando documento).

**Adequação legal/doutrinária**

- [ ] **P1** Fundamentação legal/judicial registrada no processo antes de alterar assento.

## RCPN — Certidões (`/rcpn/certidoes`, ficha `/rcpn/certidoes/<id>`)

**Apresentação/UI**

- [ ] **P2** Lista densa legível; filtros espécie, data, solicitante, selo (**RC-03**, smoke OK).

**Funcionalidade**

- [x] **P2** Molde certidão **nascimento #1** ODT/PDF — amostra OK (`--ensaio-revisao`, **MO-RC-N**).
- [ ] **P2** Moldes casamento/óbito (**MO-RC-C/O**) — ensaio **AB**; opção `--resemear` para N/C/O distintos (**RC-02**).
- [ ] **P1** Emissão (`rcpn_certidao_emitir`) — selagem `rc_certidao`; falha selador não emite certidão.
- [ ] **P2** Prévia (`rcpn_certidao_previa`) antes de selar; cancelamento (`rcpn_certidao_cancelar`) com selo TJMA + motivo.
- [ ] **P2** Impressão/PDF (`rcpn_certidao_imprimir`, `rcpn_certidao_odt`).

**Eficiência**

- [ ] **P2** Emitir da ficha do assento com tipo de certidão pré-selecionado.

**Adequação legal/doutrinária**

- [ ] **P1** Certidão negativa vs positiva — qualificação correta (Gentil; não confundir com RTD/RI).
- [ ] **P2** Inteiro teor / breve relato / 1ª via — cobrança e selo conforme tabela.

## RCPN — Folhas de segurança (`/rcpn/papel`)

**Funcionalidade**

- [ ] **P1** Receber lote (`rcpn_papel_receber`), estornar, inutilizar — trilha de auditoria.
- [ ] **P1** Consumo de folha vinculado ao assento (`rcpn_folha`, `rcpn_folha_papel`) — impedir folha já usada.
- [ ] **P2** Saldo e alerta de estoque mínimo.

**Adequação legal/doutrinária**

- [ ] **P1** Numeração de folha de segurança conforme norma estadual/CNJ.

## RCPN — Pedidos da Central (`/rcpn/pedidos`)

**Funcionalidade**

- [ ] **P1** Baixar fila (`rcpn_pedidos_baixar`) — credencial ONRCPN; erros acionáveis.
- [ ] **P1** Atender pedido: amarrar assento (`rcpn_pedido_amarrar`), emitir (`rcpn_pedido_emitir`), rejeitar/dispensar com motivo.
- [ ] **P2** Certidão eletrônica (`rcpn_certidao_eletronica_*`) — JSON, assinatura, PDF, cancelamento.

**Eficiência**

- [ ] **P2** Fila ordenada por prazo central; indicador «vence hoje».

**Adequação legal/doutrinária**

- [ ] **P2** Resposta à Central dentro dos prazos regulamentares — registrar protocolo de envio.

## RCPN — Documentos avulsos / modelos E-Ofício (`/rcpn/modelos`)

**Funcionalidade**

- [ ] **P2** Catálogo modelos livres (`rc_modelos_livres_web`) — converter, emitir por assento.
- [ ] **P2** Matriz **ABCM** RC-06 — prévia antes de imprimir.

**Adequação legal/doutrinária**

- [ ] **P2** Modelos E-Ofício não substituem termo lavrado sem ato registrário.

---

## RCPN — Nascimento

## RCPN — Registro tardio (`/rcpn/registro-tardio`)

**Funcionalidade**

- [ ] **P1** Fluxo específico RC-07 — documentos exigidos (declarações, testemunhas, mandado).
- [ ] **P2** Alertar prazo/decadência conforme legislação aplicável.

**Adequação legal/doutrinária**

- [ ] **P1** Fundamentação do registro tardio no processo/termo.

## RCPN — Gêmeos (`/rcpn/gemeos`)

**Funcionalidade**

- [ ] **P1** Vínculo entre assentos gemelares — ordem de nascimento, matrículas correlatas.
- [ ] **P2** Copiar dados comuns do 1º irmão sem duplicar folha/livro incorretamente.

## RCPN — CPF do registrado (`/rcpn/cpf`)

**Funcionalidade**

- [ ] **P1** Fila de assentos sem CPF ou CPF inválido — integração averbação CPF.
- [ ] **P2** Norma exibida (`CPFRC`) atualizada; link Receita quando aplicável.

**Adequação legal/doutrinária**

- [ ] **P1** Inclusão de CPF por averbação/anotação — não alterar fato registrado indevidamente.

---

## RCPN — Casamento

## RCPN — Habilitações (`/rcpn/habilitacoes`, ficha, nova)

**Apresentação/UI**

- [ ] **P2** Abas ou listas «1 · Habilitação» · «2 · Edital» · «3 · Prontas» (**RC-10…13**) — mesmo endpoint, navegação clara.

**Funcionalidade**

- [ ] **P1** Máquina de estados (`habilitacao.py`) — impedir pular expedir edital antes de documentos.
- [ ] **P1** Expedição habilitação selada — teste: falha selador não expede (`test_a_falha_do_selador_nao_expede_a_habilitacao`).
- [ ] **P2** Certidão de habilitação só após habilitação expedida (`test_sem_habilitacao_expedida_nao_ha_certidao`).
- [ ] **P2** Campo protocolo **e-Proclamas** na ficha (`test_a_ficha_pede_o_protocolo_do_eproclamas`).
- [ ] **P2** Habilitação vencida sai da fila «prontas» (`test_vencido_o_prazo_a_habilitacao_sai`).

**Eficiência**

- [ ] **P2** Checklist «o que falta» visível na ficha (`HAB.o_que_falta`).

**Adequação legal/doutrinária**

- [ ] **P1** Impedimentos legais (consanguinidade, casamento anterior, etc.) — registro da dispensa ou negativa.

## RCPN — Edital e e-Proclamas (`/rcpn/proclamas`, envio)

**Apresentação/UI**

- [ ] **P2** Separar **conferir** (balcão) de **enviar** (oficial/gerente) — já documentado em `proclamas_web.py`; reforçar na UI.

**Funcionalidade**

- [ ] **P1** «Testar ligação» (`/rcpn/proclamas/testar`) — health API sem token; mensagem não confundir com credencial válida.
- [ ] **P1** Envio (`rcpn_proclama_enviar`) — ordem validada em `proclamas.py`; erros `CredencialError` amigáveis.
- [ ] **P2** Fila pendentes (`PROC.pendentes`) — CNS e ambiente visíveis.

**Adequação legal/doutrinária**

- [ ] **P1** Edital de proclamas com conteúdo mínimo legal antes do envio à Central.

## RCPN — Registro do casamento (assento pós-habilitação)

**Funcionalidade**

- [ ] **P1** Ligar habilitação → assento casamento — impedir casamento sem habilitação válida salvo exceção.
- [ ] **P2** Regime de bens, pacto antenupcial, testemunhas — formulário completo.

**Adequação legal/doutrinária**

- [ ] **P1** Data/hora/local da celebração coerentes com habilitação e edital.

---

## RCPN — Óbito

## RCPN — Comunicações mensais de óbito (`/rcpn/comunicacoes`)

**Funcionalidade**

- [ ] **P1** Gerar/remeter comunicações RC-14 — cartório origem/destino, prazo mensal.
- [ ] **P2** Abrir comunicação (`rcpn_comunicacao`), resolver (`rcpn_comunicacao_resolver`).

**Adequação legal/doutrinária**

- [ ] **P1** Comunicação de óbito ao cartório do último assento (nascimento/casamento) conforme Livro I.

## RCPN — O que falta perguntar (`/rcpn/obitos-por-perguntar`)

**Funcionalidade**

- [ ] **P1** Marcas do óbito (`rcpn_marcas_do_obito`) — questionário complementar CRC/SIRC.
- [ ] **P2** Registrar respostas e limpar fila após conclusão.

**Adequação legal/doutrinária**

- [ ] **P2** Dados estatísticos (IBGE/CRC) coerentes com declaração de óbito.

---

## RCPN — Assento já lavrado (acervo e qualidade)

## RCPN — Termos a escrever (`/rcpn/termos-a-escrever`)

**Funcionalidade**

- [ ] **P2** Fila assentos lavrados sem texto do termo — prioridade por data.

## RCPN — Informações importadas (`/rcpn/informacoes-importadas`)

**Funcionalidade**

- [ ] **P2** Revisar dados importados antes de promover ao assento oficial.
- [ ] **P2** Diff importado vs digitado.

## RCPN — Importar acervo (`/rcpn/importar-acervo`)

**Funcionalidade**

- [ ] **P1** Importação em lote — log de erros por linha; não corromper numeração existente.
- [ ] **P2** Mapeamento de colunas documentado; rollback parcial.

## RCPN — CPF nos assentos antigos (`/rcpn/dados-cadastrais`)

**Funcionalidade**

- [ ] **P2** Campanha de atualização cadastral — lote + averbação assistida.

## RCPN — Matrículas (`/rcpn/matriculas`)

**Funcionalidade**

- [ ] **P1** Detectar matrícula errada/fora do padrão (**RC-22**) — corrigir com averbação/anotação.
- [ ] **P2** Relatório para envio CRC.

## RCPN — Conferência da filiação (`/rcpn/filiacao`)

**Funcionalidade**

- [ ] **P1** Lista trocas suspeitas pai/mãe/registrado — fluxo de correção (**RC-23**).
- [ ] **P2** Integração com retificação quando necessário.

---

## RCPN — Comunicações e remessas

## RCPN — O que comunicar hoje (`/rcpn/comunicacoes-painel`)

**Apresentação/UI**

- [ ] **P2** Painel RC-24 — KPIs: SIRC pendente, CRC carga, FUNAI, anotações, IBGE.

**Funcionalidade**

- [ ] **P2** Links diretos para cada fila vencida.

## RCPN — Remessa SIRC (`/rcpn/sirc`)

**Funcionalidade**

- [ ] **P1** Gerar lote, validar (`rcpn_sirc_arquivo_validar`), enviar — MRC e cancelamentos.
- [ ] **P1** Declaração inexistência (`rcpn_sirc_inexistencia`) quando mês sem movimento.
- [ ] **P2** Histórico e reprocessamento de lote com erro.

**Adequação legal/doutrinária**

- [ ] **P1** Layout e XSD vigentes CNJ — alertar versão desatualizada do gerador.

## RCPN — Comunicação FUNAI (`/rcpn/funai`)

**Funcionalidade**

- [ ] **P1** Ofício por assento (`rcpn_funai_oficio`) — template e anexos.
- [ ] **P2** Controle de envios pendentes (**RC-26**).

## RCPN — Carga CRC (`/rcpn/crc`)

**Funcionalidade**

- [ ] **P1** Montar carga (`rcpn_crc`), arquivo, enviar, marcar enviado — trilha (**RC-27**).
- [ ] **P2** Histórico (`rcpn_crc_historico`) e reenvio parcial.

## RCPN — Anotações devidas (`/rcpn/anotacoes`)

**Funcionalidade**

- [ ] **P1** Pendências de anotação CRC/CNJ — resolver (`rcpn_anotacao_resolver`) ou ofício.
- [ ] **P2** Anotação CRC dedicada (`/rcpn/anotacoes/crc`, **RC-29**).

## RCPN — Remessa IBGE (`/rcpn/ibge`)

**Funcionalidade**

- [ ] **P1** Gerar remessa estatística RC-30 — validação campos obrigatórios.
- [ ] **P2** Fechamento mensal bloqueado se SIRC/CRC críticos pendentes (configurável).

---

## RCPN — Modelos dos documentos (`/rcpn/modelos-dos-papeis`)

**Apresentação/UI**

- [ ] **P2** Separar papéis `RC_TERMO_*` vs certidões `mo_moldes` (**RC-31**, **ABCM**).

**Funcionalidade**

- [ ] **P2** Prévia papéis da casa — paridade com catálogo `modelos_da_casa.CATALOGO`.
- [ ] **P2** Herança «salvar para todos» vs cópia por serventia.

**Adequação legal/doutrinária**

- [ ] **P1** Certidões e termos sem alterar conteúdo jurídico do registro (Gentil — fidelidade).

## RCPN — Selagem, caixa e transversal

**Funcionalidade**

- [x] **P2** Selo sandbox certidão ensaio via `rc_certidao` (**RC-03**).
- [ ] **P1** Itens de emolumentos RCPN corretos por espécie (nascimento/casamento/óbito/habilitação/certidão).
- [ ] **P2** Integração protocolo geral / caixa — recibo vinculado ao ato RCPN.
- [ ] **P2** Etiqueta pós-averbação — ajuste mm/QR (`rcpn_etiqueta_averbacao_ajuste`).

**Adequação legal/doutrinária**

- [ ] **P1** Não selar ato sem lavratura/conferência; cancelamento de selo com motivo TJMA.

---


# Malote — Expedientes, tarefas e inspeções

Módulo **Operação → Malote**. Rotas `/expedientes`, `/expedientes/prontos-para-encerrar`, `/tarefas`, `/inspecoes` e fichas vinculadas; código em `app.py` com `expediente_tarefa.py` e `tarefa_processo.py`. Revisão sandbox **O1** — **ML-01…ML-04** ([MATRIZ-COBERTURA](/cursor/stores/self/docs/revisao-modulos/MATRIZ-COBERTURA.md)); UI em [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md).

**Fluxo esperado:** recebimento e protocolo interno → tarefa(s) de cumprimento → evidências/anexos → conclusão das tarefas → encerramento do expediente (`update_expediente_stage`); inspeções com responsáveis e prazos auditáveis.

---

## Malote — Expedientes (`/expedientes`)

**Apresentação/UI**

- [ ] **P2** Título de aba e `<h1>` alinhados a «Expedientes / Malote» (smoke O1).
- [ ] **P2** Empty state claro quando não há expedientes abertos ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).
- [ ] **P2** Badge/menu «Malote» com contagem de atrasos (`global_stats.overdue`) visível e com contraste quando > 0.

**Funcionalidade**

- [ ] **P1** Cadastro exige responsável principal; respeitar `require_backup_assignee` (substituto obrigatório quando configurado).
- [ ] **P1** Prazo: `deadline_start` + `deadline_days` → `deadline_date` coerente com `calc_deadline`.
- [ ] **P2** Anexos na abertura gravados em `Expedientes/<categoria>/<protocolo>` com hash registrado.
- [ ] **P2** Criação automática de tarefa vinculada quando há prazo ou categoria «para cumprimento».

**Eficiência**

- [ ] **P2** Filtros persistentes (setor, categoria, responsável, etapa, atrasados).

**Adequação legal/doutrinária**

- [ ] **P1** Trilha de auditoria (`EXPEDIENTE_CREATED`, anexos) suficiente para prestação de contas e inspeção.

## Malote — Ficha do expediente (`/expedientes/<id>`)

**Apresentação/UI**

- [ ] **P2** Bloco «O que falta para encerrar» legível (`estado` / `COMO_ENCERRAR`) — aviso, não trava indevida.
- [ ] **P2** Lista de tarefas vinculadas com status e links para dossiê.

**Funcionalidade**

- [ ] **P1** POST `/stage` só aceita etapas válidas; registra referência de resposta quando exigida.
- [ ] **P1** Encerramento não deixa expediente aberto com tarefas pendentes sem confirmação explícita do oficial.
- [ ] **P2** Upload de evidências (`/evidence`) com descrição e auditoria `ATTACHMENT_ADDED`.
- [ ] **P2** Visualização/download de anexos com integridade (SHA-256).

**Eficiência**

- [ ] **P2** Botões de ação primários acima da dobra (alterar etapa, anexar, abrir tarefa).

**Adequação legal/doutrinária**

- [ ] **P1** Metadados mínimos do expediente (origem, remetente, assunto, recebimento) preservados após encerramento.

## Malote — Prontos para encerrar (`/expedientes/prontos-para-encerrar`)

**Apresentação/UI**

- [ ] **P2** Lista dedicada com contagem no título e explicação do critério (tarefas concluídas, expediente aberto).
- [ ] **P2** Link direto para encerrar ou revisar ficha a partir da linha.

**Funcionalidade**

- [ ] **P1** Lista alimentada por `expedientes_com_tudo_concluido` — paridade com regra da ficha individual.
- [ ] **P2** Destaque de expedientes parados (> N dias prontos) configurável.

**Eficiência**

- [ ] **P2** Ação em lote: encerrar selecionados (com confirmação e motivo).

**Adequação legal/doutrinária**

- [ ] **P2** Encerramento registra usuário, data/hora e etapa final auditável.

## Malote — Tarefas (`/tarefas`, `/tarefas/<id>`)

**Apresentação/UI**

- [ ] **P2** Separar visualmente tarefas de expediente, inspeção, recorrentes e avulsas.
- [ ] **P2** Indicadores de atraso e prioridade consistentes com o painel.

**Funcionalidade**

- [ ] **P1** Conclusão de tarefa atualiza estado usado na fila «prontos para encerrar».
- [ ] **P1** Dossiê (`/dossie`) reflete histórico, anexos e vínculo `linked_expediente_id`.
- [ ] **P2** Evidências em tarefa (`/evidence`) com mesma rigorosidade de hash/auditoria do expediente.
- [ ] **P2** Responsável e substituto refletidos em notificações/listagens.

**Eficiência**

- [ ] **P2** Filtro rápido «minhas tarefas» / «setor» / «atrasadas» preservado na sessão.

**Adequação legal/doutrinária**

- [ ] **P2** Motivo e registro ao reabrir tarefa concluída (quando permitido).

## Malote — Inspeções (`/inspecoes`, `/inspecoes/<id>`)

**Apresentação/UI**

- [ ] **P2** Lista com tipo, prazo e responsável; empty state orientando cadastro inicial (`seed_inspection` no setup).

**Funcionalidade**

- [ ] **P1** Atribuição (`/atribuir`) registra responsável e prazo com auditoria.
- [ ] **P2** Vínculo opcional com tarefas/expedientes quando a inspeção exige cumprimento interno.
- [ ] **P2** Anexos e relatório de inspeção arquivados com trilha.

**Eficiência**

- [ ] **P2** Alertas de prazo integrados ao painel e ao badge Malote quando aplicável.

**Adequação legal/doutrinária**

- [ ] **P1** Dados de inspeção judicial/administrativa não permitem exclusão silenciosa — cancelamento motivado.

## Malote — Transversal (menu, painel, integrações)

**Funcionalidade**

- [ ] **P2** Widgets do painel (`/`) para expedientes abertos, tarefas e inspeções coerentes com listagens Malote.
- [ ] **P2** Recorrentes (manutenção diária) não duplicam tarefas de expediente já satisfeitas.

**Adequação legal/doutrinária**

- [ ] **P2** Perfis/roles: `/tarefas` e rotinas sensíveis respeitam `role-gated` do inventário de URLs.

---

# Livros e acervo — núcleo, numeração e cargas

Módulo **Operação → Livros e acervo**. Panorama dos **24 livros** do núcleo (`escrituracao.py` / `nu_livros`), termos de abertura e encerramento em ODT, inutilização de folhas, encerramento diário dos protocolos (Protesto, RCPJ, RTD), fixação de numeração pós-acervo, pendências de implantação e cargas E-Ofício / padrão da casa. Rotas em `nucleo_web.py` e importações em `atribuicoes_web.py`. Revisão sandbox **O6** — **OP-01…OP-07** ([MATRIZ-COBERTURA](/cursor/stores/self/docs/revisao-modulos/MATRIZ-COBERTURA.md)); inventário de URLs em [modulos-inventario-urls](/cursor/stores/self/internal/modulos-inventario-urls.md).

**Fluxo esperado:** após carga ou implantação → informar contadores que o acervo não traz (`/implantacao`, `/nucleo/numeracao`) → abrir livro da série em uso → escriturar atos → inutilizar folhas quando couber → encerrar livro físico (termo) → encerrar cada dia de protocolo → importações adicionais só com **Conferir** antes de **Importar** (irreversível).

**Base legal:** Lei **6.015/73** — escrituração, termos, sequência e publicidade dos livros registrais e protocolos (Livros I–IV conforme atribuição); Gentil — *Registros Públicos* (livros, termos, continuidade da numeração); CNJ/TJMA — exigências de inspeção sobre dias não encerrados e lacunas de folha.

---

## Livros e termos — panorama (`/nucleo/livros`)

**Apresentação/UI**

- [ ] **P2** Título de aba e `<h1>` «Livros e termos» alinhados ao menu Operação (**OP-01**).
- [ ] **P2** Panorama lista as **24 séries** com rótulo legível (RCPN A/B/C/E, RTD B, RCPJ, Notas, Protesto, protocolos diários, etc.) — smoke `test_nucleo_web`.
- [ ] **P2** Empty state quando não há livro aberto na série («nada aberto») sem parecer erro de sistema.
- [ ] **P3** Atalhos do menu lateral batem com `nucleo_livros`, encerramento diário e numeração na mesma página.

**Funcionalidade**

- [ ] **P1** POST `/nucleo/livros/abrir` grava termo de abertura e número **automático** (`numero_do_proximo_livro`) — operador não digita número do livro.
- [ ] **P1** Domínio recusa **segundo livro aberto** na mesma série (mensagem de balcão, não exceção genérica).
- [ ] **P2** Livros **diários** (`PT_PROTOCOLO`, `RG_PROTOCOLO_RCPJ`, `RG_PROTOCOLO_RTD`) exigem **dia** na abertura; série inválida recusada.
- [ ] **P2** Perfil **AUDITOR** vê panorama mas não abre livro (role-gated coerente com numeração).

**Eficiência**

- [ ] **P2** Formulário «Abrir livro» pré-seleciona série usada por último ou filtra por atribuição do operador.
- [ ] **P3** Coluna «próxima folha livre» / «último ato» visível no panorama sem abrir ficha.

**Adequação legal/doutrinária**

- [ ] **P1** Termo de abertura descreve **natureza do livro**, faixa de folhas e serventia (Lei 6.015/73; Gentil — termo inaugural).
- [ ] **P2** Um livro aberto por série espelha prática de escrituração simultânea no físico.

## Livros e termos — ficha, inutilização e encerramento (`/nucleo/livros/<id>`, termos ODT)

**Apresentação/UI**

- [ ] **P2** Ficha exibe termo de abertura, conferência (`conferir_livro`), atos na folha e inutilizações — «nada a apontar» em livro novo.
- [ ] **P2** Livro **encerrado** oculta ações «Inutilizar» e «Encerrar o livro».
- [ ] **P2** Links «Termo abertura/encerramento» em ODT com nome de arquivo previsível (`termo-abertura-rc_a-livro-1.odt`).

**Funcionalidade**

- [ ] **P1** Inutilização exige **motivo**; folha **já escriturada** ou **fora da faixa** recusada com mensagem citando limites.
- [ ] **P1** Encerramento grava termo com **folhas em branco** no meio sinalizadas na conferência prévia.
- [ ] **P1** Livro encerrado não encerra de novo; rota 404 para `termo/<qual>` inválido.
- [ ] **P2** GET `/nucleo/livros/<id>/termo/abertura|encerramento` gera ODT para colagem no livro físico (**OP-01**).
- [ ] **P2** Auditoria: `NUCLEO_LIVRO_ABERTO`, `NUCLEO_FOLHA_INUTILIZADA`, `NUCLEO_LIVRO_ENCERRADO`, `NUCLEO_LIVRO_TERMO`.

**Eficiência**

- [ ] **P2** Lista de atos na ficha paginada ou limitada (400) com aviso se houver mais.
- [ ] **P3** Atalho «Imprimir termo» abre download sem passo extra.

**Adequação legal/doutrinária**

- [ ] **P1** Inutilização com **termo/fundamento** registrado — folha não reutilizada para ato diverso (Lei 6.015/73).
- [ ] **P2** Termo de encerramento amarra **último número/folha** ao livro seguinte (continuidade Gentil).

## Encerramento diário (`/nucleo/encerramento-diario`)

**Apresentação/UI**

- [ ] **P2** Painel das **três séries diárias** com nome completo (Protesto, RCPJ, RTD) (**OP-02**).
- [ ] **P2** Indicador «encerrado hoje» vs **dias atrasados** (`dias_sem_encerrar`) visível por série.
- [ ] **P2** Histórico recente (60 encerramentos) com data, série e resumo de movimento.

**Funcionalidade**

- [ ] **P1** POST encerra dia: com movimento informa quantidade e faixa de números; **sem movimento** gera termo explícito («não houve movimento»).
- [ ] **P1** Encerrar o dia **fecha também o livro diário** daquela data (`encerrar_o_dia`).
- [ ] **P1** **AUDITOR** não encerra dia (flash de recusa).
- [ ] **P2** Domínio recusa encerrar **mesmo dia duas vezes** na mesma série.
- [ ] **P2** Panorama `/nucleo/livros` reflete dias pendentes de encerramento.

**Eficiência**

- [ ] **P2** Default de data = hoje; série escolhida uma vez por sessão.
- [ ] **P3** Link da lista de atrasados abre encerramento com série/dia pré-preenchidos.

**Adequação legal/doutrinária**

- [ ] **P1** Dia parado **escriturado como encerrado** distingue-se de dia omitido — requisito típico de inspeção/CNJ.
- [ ] **P2** Trilha `NUCLEO_DIA_ENCERRADO` com série, dia e quantidade auditável.

## Numeração dos livros (`/nucleo/numeracao`)

**Apresentação/UI**

- [ ] **P2** Lista séries do núcleo com próximo número (exceto numeração **diária**, exibida como reinício por dia) (**OP-03**).
- [ ] **P2** Destaque visual para séries marcadas `SEM_CONTADOR_NO_ACERVO` (Protesto, Registro de Protestos — pendência de acervo).
- [ ] **P2** Role-gated: perfil sem permissão não altera contador.

**Funcionalidade**

- [ ] **P1** POST `fixar_numeracao` recusa número **≤ maior já usado** (evita duplicidade de matrícula/registro/protocolo).
- [ ] **P1** Após fixar, `proximo_numero(consumir=False)` na tela reflete valor informado.
- [ ] **P2** Chaves em `nu_numeracao` aparecem mesmo vazias — operador vê lacuna antes do primeiro ato.
- [ ] **P2** Auditoria `NUCLEO_NUMERACAO` com série, valor anterior e motivo/observação.

**Eficiência**

- [ ] **P2** Campo observação («lido no Livro 9, fl. 187») obrigatório ou fortemente sugerido ao corrigir contador.
- [ ] **P3** Agrupar séries por atribuição (RCPN, RI, RTD/RCPJ, Notas, Protesto).

**Adequação legal/doutrinária**

- [ ] **P1** Primeiro ato após implantação **não** pode nascer «1» se livro físico já passou disso (defeito medido na carga — **OP-03**).
- [ ] **P2** Numeração diária de protocolo coerente com livro do dia, não contador global único.

## O que falta informar — implantação (`/implantacao`, `/implantacao/<chave>/informar`)

**Apresentação/UI**

- [ ] **P2** Título «O que falta informar» e lista **abertas** vs **fechadas** com motivo declarado na carga (**OP-04**).
- [ ] **P2** Cada pendência tipo **NUMERO** mostra contador atual de `nu_numeracao` antes do informe.
- [ ] **P3** Nome da atribuição legível (`IMP.NOME_DA_ATRIBUICAO`).

**Funcionalidade**

- [ ] **P1** Pendências vêm de `implantacao.abertas` — não adivinhadas; sistema novo sem carga = lista vazia.
- [ ] **P1** POST informar (ADMIN/MANAGER) chama `fixar_numeracao` ou registra decisão; recusa baixar contador repetido.
- [ ] **P2** Fechamento de pendência move item para histórico `fechadas` auditável (`IMPLANTACAO`).
- [ ] **P2** Login obrigatório; USER comum orientado à numeração ou ao oficial.

**Eficiência**

- [ ] **P2** Link direto da pendência RI/RCPN para tela de numeração ou importação relacionada.
- [ ] **P3** Exportar PDF da lista de pendências para ata de implantação.

**Adequação legal/doutrinária**

- [ ] **P1** Decisão de número inicial documentada — responsabilidade do oficial, não só TI (Gentil — continuidade do registro).
- [ ] **P2** Pendências de acervo E-Ofício distinguidas de «começar do zero» em serventia nova.

## Trazer acervo do E-Ofício (`/atribuicoes/importar`)

**Apresentação/UI**

- [ ] **P2** Tela ADMIN lista **caixinhas por carga** (`AC.TITULO_DA_CARGA` / `PAINEIS`) com contagens atuais (**OP-05**, smoke BLOCKED em selo).
- [ ] **P2** Caminho do acervo sqlite no disco visível (`tem_acervo`, `caminho_acervo`).
- [ ] **P2** Quadro pós-carga: inseridos vs **rejeitados com motivo** linha a linha.

**Funcionalidade**

- [ ] **P1** POST seleciona `quais` cargas; default carrega conjunto seguro quando vazio.
- [ ] **P1** **Protesto** sincroniza **ao vivo** MSSQL antes da carga (`atualizar_protesto_ao_vivo`); falha interrompe sem fallback silencioso.
- [ ] **P1** Transação única `AC.carregar_tudo`; erro `CargaError` não deixa banco inconsistente.
- [ ] **P2** Auditoria `ATRIBUICOES_CARGA` com resultado agregado.
- [ ] **P2** Após carga, operador revisa `/implantacao` e `/nucleo/numeracao` (séries sem contador no acervo).

**Eficiência**

- [ ] **P2** Permitir cargas parciais (só RCPN, só RI) para reimportação controlada.
- [ ] **P3** Estimar tempo/tamanho antes de POST em acervos grandes.

**Adequação legal/doutrinária**

- [ ] **P1** Acervo importado vira **fonte do livro** — conferir amostra de matrícula/assento/título antes de selar em produção.
- [ ] **P2** Separar carga **Notas** (`/notas/importar`) e **Protesto focado** (`/protesto/importar-eoficio`) documentado no menu — evitar dupla carga inadvertida.

## Importar de outro sistema — padrão da casa (`/importar-padrao`, `/importar-padrao/preencher`, `/importar-padrao/manual`)

**Apresentação/UI**

- [ ] **P2** Seletor de espécie (`IMPP.MODELOS`: RCPN assento, RI matrícula, RTD/RCPJ registro, Notas ato, Protesto título, Livro 3) (**OP-06**).
- [ ] **P2** **Conferir** e **Importar** como botões distintos; aviso de irreversibilidade visível.
- [ ] **P2** Upload **UTF-8** (`input type=file`) além do textarea; erro claro se encoding inválido.
- [ ] **P2** Após conferir arquivo grande, **token** preserva texto — tela não volta em branco no segundo clique (relato #31).

**Funcionalidade**

- [ ] **P1** `conferir` não grava; `importar` grava e lista recusados; **idempotência** via `origem`/`origem_chave` (não duplica).
- [ ] **P1** USER só importa **RI_MATRICULA** e **RCPN_ASSENTO**; demais espécies ADMIN/MANAGER.
- [ ] **P2** `importar_padrao_preencher` leva registro ao **formulário novo** (sessão) — não grava ato; flash «confira antes de lavrar».
- [ ] **P2** Manual markdown (`/importar-padrao/manual`) com campos da espécie para fornecedor externo.
- [ ] **P2** RCPN: importação grava **pessoas** junto do assento (CRC — sexo, município, filiação).
- [ ] **P2** Limpeza de JSON pendente > 24 h em `importacoes_pendentes`.

**Eficiência**

- [ ] **P2** Textarea oculta conteúdo > 200 KB após conferência (performance HTML).
- [ ] **P3** Link para manual da espécie ao lado do seletor.

**Adequação legal/doutrinária**

- [ ] **P1** Importação direta ≠ lavratura assistida — operador que usa «preencher formulário» assina conferência (**OP-06**).
- [ ] **P2** Campos `DA_MAQUINA` ignorados no arquivo — evita falsificação de data de registro.

## Importar matrícula do RI (`/importar-padrao?especie=RI_MATRICULA`)

**Apresentação/UI**

- [ ] **P2** Atalho de menu «Importar matrícula RI» abre mesma tela com espécie **RI_MATRICULA** pré-selecionada (**OP-07**).
- [ ] **P2** Quadro de conferência mostra CNM/chave e campos obrigatórios RI antes de importar.

**Funcionalidade**

- [ ] **P1** Registro entra em `ri_matriculas`; ficha `/registro-imoveis` localiza por número/CNM ([05-ri](/cursor/stores/self/docs/revisao-modulos/05-ri.md)).
- [ ] **P1** Conferir detecta colisão com matrícula já existente (recusa com motivo).
- [ ] **P2** Opção «preencher» redireciona a `ri_nova_matricula` sem gravar — fluxo de acervo Word/legado.
- [ ] **P2** USER pode executar importação/conferência (perfil balcão RI).

**Eficiência**

- [ ] **P2** Amostra de linhas aceitas/recusadas no quadro pós-conferência exportável (CSV).
- [ ] **P3** Atalho pós-importação para ficha da matrícula recém-entrada.

**Adequação legal/doutrinária**

- [ ] **P1** Numeração/CNM importados alinhados ao **Livro 2** físico — cruzar com `/registro-imoveis/numeracao` após lote.
- [ ] **P2** Matrícula importada não dispensa averbações obrigatórias posteriores (Lei 6.015/73, Liv. III RI).

## Livros e acervo — transversal (menu, notas, RI, auditoria)

**Funcionalidade**

- [ ] **P2** Livros **Notas** (`/notas/livros`) e **núcleo** (`/nucleo/livros`) — operador entende qual menu usar (atribuição vs operação).
- [ ] **P2** Pós-`/notas/importar`: desambiguar folhas e reconciliar folha corrente do livro trazido do E-Ofício.
- [ ] **P2** Correção pontual de acervo (`/administrativo/acervo/corrigir`, **OP-08**) linkada na ajuda deste módulo.
- [ ] **P2** Widgets do painel `/` não contradizem «dias sem encerrar» do encerramento diário.

**Adequação legal/doutrinária**

- [ ] **P2** Termos ODT do núcleo seguem padrão visual dos termos Notas (`/notas/livros/.../termo`) — identidade da serventia.
- [ ] **P2** CSRF e roles em todas as rotas POST de livro/numeração/carga conforme inventário.

---

# Notas — Tabelionato de Notas

Módulo **Atribuições → Tabelionato de Notas**. Rotas sob `/notas/*`; código em `notas_web.py`, `notas_livro.py`, `notas_doi.py`, `notas_schema.py`, templates `notas_*`. Revisão sandbox **O2** — **NT-01…NT-15** ([03-notas](/cursor/stores/self/docs/revisao-modulos/03-notas.md), [MATRIZ-COBERTURA](/cursor/stores/self/docs/revisao-modulos/MATRIZ-COBERTURA.md)); inventário em [modulos-inventario-urls](/cursor/stores/self/internal/modulos-inventario-urls.md); UI em [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md).

**Fluxo esperado (balcão):** cartão/sinal → reconhecimento ou autenticação → selo + etiqueta · **Instrumentos:** minuta (`nt_modelos`) → lavratura no livro → teor ODT/traslado → selo(s) → remessa centrais quando couber · **Escritura com imóvel:** qualificar partes na ficha → DOI mensal → CTP/RI quando integrado.

**Base legal/doutrinária:** **Lei nº 6.015/73** (livros e termos notariais); **Código Civil** e normas CNJ/TJMA sobre escrituras, procurações e reconhecimento; **DOI** (Instrução Normativa RFB); **Alberto Gentil** — atos notariais, publicidade e sequência dos livros *(capítulos de tabelionato na edição da serventia)*.

---

## Notas — Painel do tabelionato (`/notas`) — NT-01

**Apresentação/UI**

- [x] **P3** Título de aba por família de instrumentos coerente («Escrituras — Notas», etc.) (**N-01**, 3.6.187/193).
- [ ] **P2** Indicador de **selos pendentes** / fila selador na primeira dobra ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).
- [ ] **P2** Atalhos do painel espelham submenu (balcão · instrumentos · consulta) sem duplicar rotas mortas.

**Funcionalidade**

- [ ] **P2** Números do painel (atos do dia, pendências) batem com listas reais — smoke O2.
- [ ] **P2** Links para `/notas/escrituras/pendentes` quando houver minuta parada.

**Eficiência**

- [ ] **P2** Últimos reconhecimentos / últimos atos lavrados (atalho operador).

**Adequação legal/doutrinária**

- [ ] **P2** Avisos legais do painel não contradizem manual da serventia (semelhança vs autenticidade).

## Notas — Reconhecer firma (`/notas/reconhecimento`) — NT-02

**Apresentação/UI**

- [x] **P2** Caixa didática semelhança/autenticidade **recolhível** após primeira leitura (`cg-didatica-recolhivel`, **critica-telas**).
- [ ] **P2** Abas «Reconhecimentos feitos» / «Cartões» vs submenu lateral — reduzir duplicidade mental de navegação.
- [ ] **P3** Busca por nome/CPF com feedback quando cartão bloqueado (checkbox «ciente» visível).

**Funcionalidade**

- [ ] **P1** POST reconhecer valida cartão ativo, espécie e flags veículo/financeiro antes de selar.
- [ ] **P1** Falha de selo **não** grava reconhecimento — mensagem acionável (smoke #5, **NT-02**).
- [ ] **P2** Etiqueta HTML imprimível `GET /notas/reconhecimento/<id>/etiqueta` com QR alinhado ao selo sandbox.

**Eficiência**

- [ ] **P2** Reutilizar último cartão/apresentante frequente.
- [ ] **P2** Atalho «+ Reconhecer» preserva filtros da lista.

**Adequação legal/doutrinária**

- [ ] **P1** Distinção **por semelhança** vs **por autenticidade** registrada no teor/etiqueta (responsabilidade tabelião; Gentil — fé pública).

## Notas — Autenticar cópia (`/notas/autenticacao`) — NT-03

**Apresentação/UI**

- [ ] **P2** Título e `<h1>` «Autenticar cópia» — paridade com reconhecimento.
- [ ] **P2** Campos de folhas/páginas autenticadas agrupados (evitar erro de contagem).

**Funcionalidade**

- [ ] **P1** Contagem de folhas autenticadas coerente com tabela de emolumentos TJMA.
- [ ] **P2** Vínculo opcional a protocolo/caixa quando autenticação é cobrada em depósito.

**Eficiência**

- [ ] **P2** Default «quantidade» = 1, editável; último tipo de documento.

**Adequação legal/doutrinária**

- [ ] **P1** Autenticação não substitui reconhecimento de firma em documento exigido autenticado + firmado.

## Notas — Escrituras públicas (`/notas/escrituras`) — NT-04

**Apresentação/UI**

- [x] **P3** Cabeçalho da família com **título único** (`notas_familia.html`, 3.6.192) — sem duplicar «Escrituras» no `<h1>` e na aba.
- [ ] **P2** Lista + atalho «Lavrar» + modelos na mesma tela — orientar roteiro minuta→lavratura (**N-02**).
- [ ] **P2** Filtros (situação, livro, data) preservados na paginação.

**Funcionalidade**

- [ ] **P1** Lavratura completa ensaio — fechar lacuna **C** dependente de minuta→selo ([03-notas](/cursor/stores/self/docs/revisao-modulos/03-notas.md), **MO-NT-MIN** AB).
- [ ] **P2** Pendências (`/notas/escrituras/pendentes`) listam só minutas/atos incompletos com motivo.
- [ ] **P2** Prévia de minuta antes de lavrar (`nt_modelos`).

**Eficiência**

- [ ] **P2** «Usar modelo» abre `/notas/atos/novo` com `familia=escrituras` e código pré-selecionado.

**Adequação legal/doutrinária**

- [ ] **P1** Checklist de requisitos do modelo (cláusulas, testemunhas, ITBI quando couber) visível na escolha do modelo.

## Notas — Atas notariais (`/notas/atas`) — NT-05

**Apresentação/UI**

- [ ] **P2** Paridade visual com família escrituras (mesmo `notas_familia.html`).

**Funcionalidade**

- [ ] **P2** Lavratura e teor ODT seguem série/livro de atas configurado.
- [ ] **P2** Vínculo a ata de assembleia/convenção quando modelo exige anexos.

**Eficiência**

- [ ] **P3** Atalho copiar dados de ata anterior (mesma pessoa jurídica).

**Adequação legal/doutrinária**

- [ ] **P1** Ata notarial respeita requisitos de deliberação (CC/Lei 6.015 — forma pública).

## Notas — Atos de livro (`/notas/atos`, ficha `/notas/atos/<id>`) — NT-06

**Apresentação/UI**

- [ ] **P2** Ficha separa **Teor** · **Livro/folha** · **Selos** · **DOI** · **Depósito** · **Anexos** (details já usados — manter ordem sugerida).
- [ ] **P2** Badge «sem teor» / «lavrado» / «selado» no cabeçalho.

**Funcionalidade**

- [x] **P1** Bloco **DOI — lados das partes** (alienante/adquirente) na ficha do ato com conferência `notas_doi.conferir_participacoes` (3.6.193).
- [x] **P1** Selo **16.39** (arquivamento) opcional na lavratura + rota `POST /notas/atos/<id>/selar-arquivamento` se pendente (3.6.192).
- [x] **P2** **Depósito prévio** na lavratura: mesmo registro do caixa, consumo/baixa sem segundo lançamento (3.6.192).
- [x] **P2** Lançamento no livro até folha **`2v`** quando texto ocupa frente e verso (`notas_livro`, testes `test_notas_lancamento_web`) (3.6.192).
- [ ] **P1** `GET /notas/atos/<id>/teor.odt` — amostra #1 OK; manter paridade após editar teor.
- [ ] **P2** Inutilização de folhas coerente com faces `Nv` (`notas_livro.py`).

**Eficiência**

- [ ] **P2** Prévia HTML/PDF do teor antes de selar.
- [ ] **P2** Atalho «Gerar traslado» pós-lavratura quando PA-NOTAS_TRASLADO fechar seed.

**Adequação legal/doutrinária**

- [ ] **P1** Sequência livro/folha/termo sem lacuna (Lei 6.015/73; Gentil — continuidade).
- [ ] **P1** Ato **com imóvel** exige bloco DOI preenchido ou marcação explícita «sem imóvel» antes de fechar mês.

## Notas — Cartões de autógrafo (`/notas/cartoes`) — NT-07

**Apresentação/UI**

- [ ] **P2** Ficha do cartão: foto/scan legível; status bloqueado destacado.

**Funcionalidade**

- [ ] **P1** Bloqueio impede reconhecimento salvo confirmação explícita.
- [ ] **P2** Impressão ficha cartão (`PA-NOTAS_CARTAO_FICHA` AB) — seed para ensaio.

**Eficiência**

- [ ] **P2** Busca tolerante a acento; CPF formatado.

**Adequação legal/doutrinária**

- [ ] **P2** Cartão arquivado conforme normas internas — trilha de quem alterou bloqueio.

## Notas — Sinais públicos (`/notas/sinais`, `/notas/sinais/reconhecimento`) — NT-08 / NT-09

**Funcionalidade**

- [ ] **P2** Cadastro de sinal vinculado a pessoa; reconhecimento de sinal integrado ao fluxo firma quando checkbox marcada.
- [ ] **P2** Lista de sinais ativos/inativos.

**Eficiência**

- [ ] **P3** Atalho do reconhecimento de firma para cadastrar sinal inexistente.

**Adequação legal/doutrinária**

- [ ] **P2** Reconhecimento de sinal público documentado no instrumento lavrado.

## Notas — Pendências das escrituras (`/notas/escrituras/pendentes`) — NT-10

**Apresentação/UI**

- [ ] **P2** Critério da lista explícito no `<h1>` (minuta sem lavrar, selo pendente, DOI incompleta).

**Funcionalidade**

- [ ] **P1** Cada linha abre ficha com ação sugerida (completar teor, selar, DOI).
- [ ] **P2** Excluir atos cancelados/arquivados.

**Eficiência**

- [ ] **P2** Ordenação por prazo/protocolo.

## Notas — Livros do tabelionato (`/notas/livros`) — NT-11

**Apresentação/UI**

- [ ] **P2** Diferenciar visualmente de `/nucleo/livros` (atribuição vs operação) — link cruzado na ajuda.

**Funcionalidade**

- [ ] **P1** Abertura/encerramento de livro notarial com termo ODT (`PA-NOTAS_TERMO_LIVRO` AB).
- [ ] **P2** Folha corrente vs último ato lavrado — alerta de divergência pós-import E-Ofício.

**Eficiência**

- [ ] **P2** Atalho «Lavrar ato neste livro» com livro pré-selecionado.

**Adequação legal/doutrinária**

- [ ] **P1** Termo de abertura/encerramento conforme Lei 6.015/73 e prática Gentil.

## Notas — Remessa às centrais (`/notas/remessas`) — NT-12

**Funcionalidade**

- [ ] **P1** Montar remessa simulada/produção com log de retorno ([08-selo-centrais](/cursor/stores/self/docs/revisao-modulos/08-selo-centrais.md)).
- [ ] **P2** Conferência selos/emolumentos antes de fechar remessa.

**Eficiência**

- [ ] **P2** Reenvio parcial de itens recusados.

**Adequação legal/doutrinária**

- [ ] **P1** Prazos CNJ/TJMA para envio — aviso quando remessa atrasada.

## Notas — Ajustar etiqueta (`/notas/etiqueta/ajuste`) — NT-13

**Funcionalidade**

- [ ] **P2** Mesmo pipeline mm/QR do reconhecimento (#5) aplicável a outros atos notariais.
- [ ] **P3** Página de teste de impressão lado a lado com ajuste.

## Notas — Trazer notas do E-Ofício (`/notas/importar`) — NT-14

**Apresentação/UI**

- [ ] **P2** Aviso **BLOCKED** em sandbox sem E-Ofício — mensagem clara (matriz **NT-14**).

**Funcionalidade**

- [ ] **P1** Conferir antes de importar; reconciliar folhas após carga (transversal Livros e acervo).
- [ ] **P1** Role-gated — apenas perfis de implantação.

## Notas — Modelos dos documentos (`/notas/modelos`) — NT-15

**Apresentação/UI**

- [ ] **P2** Separar papéis `NOTAS_*` (`modelos_da_casa`) vs minutas `nt_modelos` (**ABCM**).

**Funcionalidade**

- [ ] **P2** Prévia papéis — paridade [MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md) (PA-NOTAS_* AB).
- [ ] **P2** Governança «salvar para todos» vs cópia por serventia.

**Adequação legal/doutrinária**

- [ ] **P1** Minutas não introduzem cláusulas ilegais — revisão oficial antes de «salvar para todos».

## Notas — Selagem, caixa e transversal

**Funcionalidade**

- [ ] **P1** Selo do ato notarial + selo arquivamento **não** duplicam numeração (`nt_atos.selo` vs `selo_arquivamento`).
- [ ] **P2** Integração protocolo geral / recibo caixa nos atos cobrados em balcão.
- [ ] **P2** Export DOI mensal inclui escrituras marcadas «com imóvel» — cruzar com `/registro-imoveis/doi` quando serventia unificar arquivo.

**Eficiência**

- [ ] **P2** Lista `/selos` filtrável por atribuição Notas.

**Adequação legal/doutrinária**

- [ ] **P1** Não selar sem lavratura; recuperação de selo com motivo TJMA.

---

# Protesto — cartório de protesto (Lei 9.492/97)

Módulo **Atribuições → Protesto**. Rotas sob `/protesto/*`; código em `atribuicoes_web.py` com `cenprot_web.py`, integrações **CRA21**, **Resolve** (intimação digital), templates `protesto_*`. Revisão sandbox **O5** — **PT-01…PT-16** ([07-protesto](/cursor/stores/self/docs/revisao-modulos/07-protesto.md)); inventário [modulos-inventario-urls](/cursor/stores/self/internal/modulos-inventario-urls.md); UI [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md).

**Fluxo esperado:** apresentação do título → cadastro/intimação (CRA/CENPROT/Resolve) → protesto ou devolução → instrumento/termo → certidões → remessas CRA/CENPROT → encerramento diário protocolo protesto (`/nucleo/encerramento-diario`).

**Base legal:** **Lei nº 9.492/97**; edital/intimação conforme **CRA estadual**; **CENPROT** nacional; CNJ/TJMA — emolumentos e selos; Gentil — publicidade e sequência do registro de protesto *(quando aplicável na edição da serventia)*.

---

## Protesto — O roteiro das Centrais (`/protesto/roteiro`) — PT-01

**Apresentação/UI**

- [ ] **P2** Página longa (CRA + CENPROT + notas legais) — sumário fixo ou âncoras ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).
- [ ] **P2** Coluna «Hoje» com zeros — reforçar copy explicativa no topo quando contadores zerados.

**Funcionalidade**

- [ ] **P2** Horários CRA e passos operacionais atualizáveis pela serventia (config/admin).

**Eficiência**

- [ ] **P3** Links diretos para remessa CRA, pendências CENPROT e intimação digital.

**Adequação legal/doutrinária**

- [ ] **P2** Roteiro reflete Lei 9.492 e manual CRA-MA — data da última revisão visível.

## Protesto — Títulos (`/protesto`) — PT-02

**Apresentação/UI**

- [x] **P2** Redirect legado **`/protesto/titulos` → `/protesto`** (**PR-01**, 3.6.188) — bookmarks antigos.
- [ ] **P2** Título de aba «Protesto — títulos» alinhado ao menu (3.6.193 transversal).
- [ ] **P2** Filtros (situação, apresentante, vencimento) preservados.

**Funcionalidade**

- [ ] **P1** Busca por número, devedor, protocolo, nosso número CRA.
- [ ] **P2** Ficha título **#1–#3** HTML amostra OK — manter após seed ([07-protesto](/cursor/stores/self/docs/revisao-modulos/07-protesto.md)).
- [ ] **P2** Avisos múltiplos por título (lista, não só um campo).

**Eficiência**

- [ ] **P2** Atalho «+ Novo título» com defaults da última apresentação.

**Adequação legal/doutrinária**

- [ ] **P1** Situações (apresentado, intimado, protestado, sustado, cancelado) coerentes com Lei 9.492.

## Protesto — Ficha do título (`/protesto/<titulo_id>`)

**Apresentação/UI**

- [ ] **P2** Seções: **Apresentação** · **Devedores** · **Intimações** · **Protesto/sustação** · **Selos** · **CRA/CENPROT** · **Anexos**.

**Funcionalidade**

- [ ] **P1** Transições de estado com motivo mínimo e auditoria (`PROTESTO_*`).
- [ ] **P2** Imagens do título (`/protesto/imagens`) linkadas na ficha.
- [ ] **P2** Instrumento/termo gerável quando estado apto (**PA-PT_*** AB).

**Eficiência**

- [ ] **P2** Timeline de eventos (intimação, edital, protesto) ordenada.

**Adequação legal/doutrinária**

- [ ] **P1** Prazos de intimação/edital registrados — fundamento em caso de sustação judicial.

## Protesto — Certidões (`/protesto/certidoes`) — PT-03

**Apresentação/UI**

- [ ] **P2** Empty state orientando emitir certidão a partir do título.

**Funcionalidade**

- [ ] **P1** Seed `pt_certidoes` para ensaio — hoje **0** registros ([07-protesto](/cursor/stores/self/docs/revisao-modulos/07-protesto.md)).
- [ ] **P2** Emissão negativa/positiva/cancelamento (`PA-PT_CERT_*` AB) com selo.
- [ ] **P2** Busca por nome de consultado vinculada a títulos/devedores.

**Eficiência**

- [ ] **P2** Reemitir certidão com mesmos dados (evitar re-digitar).

**Adequação legal/doutrinária**

- [ ] **P1** Certidão descreve exatamente situação do título (Lei 9.492) — sem linguagem ambígua.

## Protesto — Instrumentos (`/protesto/instrumentos`) — PT-04

**Funcionalidade**

- [ ] **P1** ODT instrumento de protesto — seed ensaio (**PA-PT_INSTRUMENTO** AB).
- [ ] **P2** Lista instrumentos pendentes vs lavrados.

**Eficiência**

- [ ] **P2** Abrir ficha do título a partir da linha.

**Adequação legal/doutrinária**

- [ ] **P1** Instrumento contém elementos exigidos pelo CRA/TJMA.

## Protesto — Remessa da CRA (`/protesto/remessas`) — PT-05

**Funcionalidade**

- [ ] **P1** Remessa CRA completa — pendente simulador (**PR-02**, [07-protesto](/cursor/stores/self/docs/revisao-modulos/07-protesto.md)).
- [ ] **P2** Log de envio/retorno por arquivo.

**Eficiência**

- [ ] **P2** Reprocessar apenas títulos recusados.

**Adequação legal/doutrinária**

- [ ] **P1** Layout arquivo CRA-MA validado antes do envio.

## Protesto — Imagens dos títulos (`/protesto/imagens`) — PT-06

**Funcionalidade**

- [ ] **P2** Upload/preview PDF ou imagem por título.
- [ ] **P2** Hash/integridade para remessa CRA.

## Protesto — Avisos e editais (`/protesto/avisos`) — PT-07

**Funcionalidade**

- [ ] **P1** Geração de edital conforme CRA — publicação registrada.
- [ ] **P2** Vínculo edital ↔ título(s) protestandos.

**Adequação legal/doutrinária**

- [ ] **P1** Edital observa requisitos de publicidade (Lei 9.492 + normas CRA).

## Protesto — Desistências (`/protesto/desistencias`) — PT-08

**Funcionalidade**

- [ ] **P1** Registrar desistência com data e efeito no título.
- [ ] **P2** Lista filtrável por período.

## Protesto — A protestar (`/protesto/a-protestar`) — PT-09

**Funcionalidade**

- [ ] **P1** Fila de títulos aptos após intimação/edital — ação «Protestar» com selo.
- [ ] **P2** Bloquear protesto se pendência CENPROT/CRA aberta.

## Protesto — Retorno à CRA (`/protesto/retornos`) — PT-10

**Funcionalidade**

- [ ] **P1** Importar/processar retorno CRA — atualizar situação local.
- [ ] **P2** Relatório de divergências.

## Protesto — CRA API (`/protesto/cra/api`) — PT-11

**Funcionalidade**

- [ ] **P1** Credenciais role-gated; teste de ligação com mensagem acionável.
- [ ] **P2** Não duplicar título ao sincronizar.

## Protesto — Pendências CENPROT (`/protesto/cenprot/pendencias`) — PT-12

**Apresentação/UI**

- [x] **P2** Atalho/redirect **SC-01** corrigido (3.6.189) — menu leva à fila certa.

**Funcionalidade**

- [ ] **P1** Resolver pendência registra retorno CENPROT (`cenprot_web.py`).
- [ ] **P2** Guard `protesto_` impede mistura com outras atribuições.

## Protesto — Intimação Digital (`/protesto/resolve`) — PT-13

**Funcionalidade**

- [ ] **P1** Envio Resolve com chave/config válida — trilha de protocolo.
- [ ] **P2** Reenvio quando intimação expirada.

**Adequação legal/doutrinária**

- [ ] **P1** Intimação digital só quando habilitada pelo credor/norma — registro do meio.

## Protesto — Chave CENPROT (`/protesto/cenprot`) — PT-14

**Funcionalidade**

- [ ] **P1** Armazenamento seguro da chave; mascarar na tela.
- [ ] **P2** Teste de autenticação CENPROT isolado de produção quando simulador.

## Protesto — Importar E-Ofício (`/protesto/importar-eoficio`) — PT-15

**Funcionalidade**

- [ ] **P1** Sincronização **ao vivo** MSSQL antes da carga (`atualizar_protesto_ao_vivo`) — falha interrompe (transversal Livros).
- [ ] **P2** Documentar diferença vs `/atribuicoes/importar` — evitar dupla carga.

## Protesto — Modelos dos documentos (`/protesto/modelos`) — PT-16

**Funcionalidade**

- [ ] **P2** Catálogo `PT_*` — cinco papéis AB ([MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md)).
- [ ] **P2** Prévia instrumento/certidão antes de produção.

**Adequação legal/doutrinária**

- [ ] **P1** Modelos de certidão compatíveis com Lei 9.492 (negativa/positiva/cancelamento).

## Protesto — Selagem, caixa e transversal

**Funcionalidade**

- [ ] **P1** Emolumentos por espécie (apresentação, intimação, protesto, certidão) — tabela TJMA.
- [ ] **P2** Encerramento diário protocolo protesto alinhado a `/nucleo/encerramento-diario` (**OP-02**).
- [ ] **P2** Widget painel `/` coerente com fila «a protestar».

**Adequação legal/doutrinária**

- [ ] **P1** Cancelamento/sustação com fundamento registrado — trilha para certidão posterior.

---

# Registro de Imóveis (RI)

Módulo **Atribuições → Registro de Imóveis** (34 entradas de menu em 7 grupos; ~157 rotas `/registro-imoveis/*`, `/ri/*`, `/livro3/*`, `/usucapiao/*` + 4 rotas CNIB). Código: `ri_web.py` (~477 KB), `ri_schema.py`, `ri_odt.py`, `ri_modelos_atos.py`, `ri_minuta.py`, `ri_rascunho.py`, `ri_revisao*.py`, `ri_numeros_do_teor.py`, `ri_expurgo.py`, `ri_digitalizacao.py`, `ri_imagens.py`, `ri_doc*.py`, `ri_cnm.py`, `ri_cnib.py`, `cnib_web.py`, `ri_onr*.py`, `onr_api.py`, `onr_endereco_*.py`, `onr_carga.py`, `ri_ctp.py`, `notas_doi.py` (DOI), `usucapiao*.py`, `retificacao*.py`, `ra_*.py` (Livro 3) e `atribuicoes_web.py` (lista/novo/lançar do Livro 3 e certidões L3). Revisão sandbox **O4** — **RI-01…RI-21**, **L3-01…L3-04**, **US-01/US-02**, **RI-CNIB-01…03**, **RI-ONR-01…04**, rotas-filhas **RX-06/RX-07** ([05-ri](/cursor/stores/self/docs/revisao-modulos/05-ri.md), [MATRIZ-COBERTURA](/cursor/stores/self/docs/revisao-modulos/MATRIZ-COBERTURA.md)); ONR em [inventario-onr-cartorio-gestao](/cursor/stores/self/docs/integracoes/inventario-onr-cartorio-gestao.md), [onr-decisoes-e-lote-endereco](/cursor/stores/self/docs/integracoes/onr-decisoes-e-lote-endereco.md) e [onr-plano-execucao-resultados](/cursor/stores/self/docs/integracoes/onr-plano-execucao-resultados.md); Livro 3 em [livro3-ficha-formatacao](/cursor/stores/self/docs/livro3-ficha-formatacao.md); papéis em [MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md) e [CHECKLIST-COMPARATIVO-SELADO](/cursor/stores/self/docs/revisao-modulos/CHECKLIST-COMPARATIVO-SELADO.md); UI em [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md); revisão interna do código `REVISAO_MODULO_RI.md` (13/08/2026).

**Fluxo esperado (o dia):** apresentação do título → **protocolo/prenotação** no Livro 1 (número de ordem, hora, prazo de 20 dias úteis ou 40 na REURB-S) + **depósito prévio** no caixa → **qualificação** em até 10 dias úteis → **nota devolutiva** (exigências de uma só vez) *ou* **minuta/rascunho** → **lavratura** R/AV na matrícula (numeração contínua) → **revisão antes de selar** → **selo** (o ato fica suspenso se o selo não sair) → **selo de arquivamento 16.39** encerra a prenotação → **ficha/certidão** → **remessas** (DOI, CTP, ONR indicador real/pessoal, CNIB).

**Processos longos:** usucapião extrajudicial (Lei 6.015, art. 216-A; TJMA 747–761) e retificação de área (arts. 212–213; TJMA 587–605) — a prenotação deveria ficar prorrogada até a decisão (TJMA 452, § 3º, IV).

**Números medidos no próprio código (comentários de produção, ago–set/2026):** 1.982 matrículas; `digi_path` vazio em 1.982/1.982; 370 certidões de inteiro teor já emitidas; `ri_protocolos.ato_id` nulo em 784/784 prenotações históricas; atos dentro do texto em 1.052 de 1.508 fichas com teor (743 ACERVO exigem número manual, 13 ESTRUTURADAS numerariam sozinhas); 71% das partes sem CPF/CNPJ; ~1.443 fichas com teor e sem endereço estruturado (fila ONR); 1.241 atos herdados sem natureza do título; CNIB: 0 coincidências por CPF/CNPJ e 6 por nome (homônimos) em 10 matrículas.

**Base legal/doutrinária:** **Lei nº 6.015/73, Título V** (Registro de Imóveis, arts. 167 e seguintes) — livros do art. 173 (1 Protocolo, 2 Registro Geral, 3 Auxiliar, 4 Indicador Real, 5 Indicador Pessoal), matrícula (arts. 176 e 227–235), prioridade e títulos contraditórios (arts. 182–192), prenotação (art. 205), qualificação e dúvida (arts. 198–204), certidões (arts. 16–21), retificação (arts. 212–213), usucapião (art. 216-A), adjudicação compulsória (art. 216-B), com a **Lei 14.382/2022** (SERP); **Provimento CNJ 149/2023** (CNN — ONR/SAEC, CNIB, usucapião, que incorporou o Prov. 65/2017); **Código de Normas TJMA, Parte Especial, Cap. III, arts. 424–773** — livros 424–435, procedimento 436–545, certidões 546–559, retificação 587–605, usucapião 747–761, cédulas 762–773 ([codigo-normas-tjma-atualizado.pdf](/cursor/stores/self/docs/reference/codigo-normas-tjma-atualizado.pdf); índice em [codigo-normas-tjma-indice](/cursor/stores/self/internal/conhecimento-cartorio/codigo-normas-tjma-indice.md)); **Alberto Gentil, *Registros Públicos*** — parte do Registro de Imóveis: princípios registrais (instância/rogação, prioridade, especialidade objetiva e subjetiva, continuidade, legalidade/qualificação, disponibilidade, publicidade e fé pública, concentração, unitariedade da matrícula), matrícula e seus atos (registro × averbação), certidões e publicidade registral *(PDF não localizado em `Downloads` neste ambiente — citar pelo capítulo e confirmar a página na edição da serventia)*.

---

## RI — Concluído na 3.6.193 (não reabrir salvo regressão)

- [x] **Livro 3 — ficha `.odt` com cabeçalho** da serventia (brasão + grade REGISTRO Nº / LIVRO Nº 3 — REGISTRO AUXILIAR / FLS. / USUÁRIO) e corpo completo (natureza, CNM, parcelas, vencimentos, partes, rodapé «não é certidão») — `ra_ficha_odt.cabecalho_ficha_livro3_odf`, rota `/livro3/<id>/ficha.odt` ([livro3-ficha-formatacao](/cursor/stores/self/docs/livro3-ficha-formatacao.md)).
- [x] **Livro 3 — certidão** alinhada ao molde do Livro 2 (3.6.188+) e **digitalização** do registro e do ato (`/livro3/<id>/digitalizacao`, `/livro3/ato/<id>/digitalizacao`) — release 3.6.193.
- [x] **ONR — testes de tela** `test_ri_indicador_real_web`, `test_ri_indicador_pessoal_web`, `test_ri_onr_export_web` com fixture `cg_casa_logada` e URLs `/registro-imoveis/...` (**RI-ONR-01**, 4 passed; gate do release).
- [x] **ONR — baseline pytest** `test_onr_api`, `test_ri_onr_central`, `test_onr_endereco_do_teor`, `test_onr_endereco_telas` — **130 passed** (23/09/2026).
- [x] **Títulos de aba RI** derivados do rótulo do menu (`titulo_aba.sugerir`; `test_titulo_aba` cobre `ri_matriculas` e `ri_protocolo`) — ex.: «Protocolo (Livro 1-A) — Registro de Imóveis».
- [x] **Prenotação — prazo gravado** (20 dias úteis / 40 REURB-S, TJMA 436 e 452) usado no comprovante e na lista, sem constante fixa; reabrir protocolo **não** devolve prazo (conferido no código 3.6.193).
- [x] **Selo de arquivamento 16.39** encerra a prenotação do ato; lavrar **não** encerra, para os atos seguintes do mesmo título (conferido no código 3.6.193).
- [x] **Certidão gratuita** exige motivo escrito (≤ 500 caracteres, limite TJ `motivoIsentoGratuito`) antes de criar a certidão (conferido no código 3.6.193).
- [x] **Modelos de atos — defeitos da revisão de 13/08** conferidos no código 3.6.193: escolha `{A | B}` no lugar do colchete aninhado; `R-ALIENACAO-FIDUCIARIA` sem o parágrafo de consolidação; `R-USUCAPIAO` sem requisito de transmitente/continuidade; `R-TITULO-DOMINIO` sem a citação errada `167, I, 26`.

---

## RI — Menu e navegação do módulo

**Apresentação/UI**

- [ ] **P2** Menu com 34 entradas (usucapião, ONR, CNIB e Livro 3 no mesmo módulo) — curva de aprendizado alta ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)); oferecer visão «balcão» (O dia + Consulta) e visão «oficial» (tudo) por perfil.
- [ ] **P2** Grupo **Modelos** aparece duas vezes no menu (Modelos de atos / Modelos de documento do RI e, depois de Configuração, Modelos dos documentos `/ri/modelos`) — unificar sob um cabeçalho.
- [ ] **P2** Telas fora do menu caem no título genérico da serventia (sem `block title`): `ri_protocolo_ver`, `ri_nota`, `ri_editar`, `ri_nova`, `ri_preencher`, `ri_conferir`, `ri_expurgo`, `usucapiao_ficha`, `usucapiao_dossie` e a lista do Livro 3 (`atrib_lista.html`) — título com o número (ex.: «Protocolo 11.548 — RI»).
- [ ] **P3** Rótulo «Usucapião &mdash; o que o Código de Normas exige» chega cru (entidade HTML) ao mapa do menu/inventário — normalizar para «—».
- [ ] **P3** Busca única no topo do módulo (matrícula, protocolo, pessoa) — hoje são três telas (lista, indicador real, indicador pessoal).

**Funcionalidade**

- [x] **P1** *(sandbox 3.6.195 — ONR, Next Cloud, imagens, numeração, delegatários, cancelar certidão, organizar digitalizações e ajustes CNIB só ADMIN/MANAGER)* Alinhar **papel do menu × papel da rota**: o menu esconde «Exportação ONR» e «Fichas digitalizadas» de USER, mas `ri_onr`, `ri_onr_next_cloud` e `ri_resolver_imagens` aceitam USER no `@roles_required` (acesso por URL direta) — decidir e igualar.
- [ ] **P2** Contadores no menu RI: prenotações vencendo (≤ 3 dias úteis), notas de revisão abertas, CNIB aguardando okay, endereços ONR a conferir.

**Adequação legal/doutrinária**

- [ ] **P2** «Ajuda desta tela» citar o artigo do Código TJMA de cada fluxo (prenotação 452, certidões 546–559, usucapião 747–761), padrão já usado em usucapião e retificação.

## RI — Protocolo / prenotação (`/registro-imoveis/protocolo`) — RI-01

**Apresentação/UI**

- [ ] **P2** Coluna «faltam N dias úteis» com cor (verde/amarelo/vermelho) e filtro «vencem esta semana».
- [ ] **P2** Empty state com a fila zerada (não exercitado na crítica) — mensagem e atalho «Prenotar título».
- [ ] **P3** Exibir a **hora** da prenotação na lista (coluna `hora` existe) — decide a prioridade entre títulos do mesmo dia.

**Funcionalidade**

- [x] **P1** *(sandbox 3.6.195, mínimo — suspender/retomar manual em `/registro-imoveis/protocolo/<id>/prazo`, `ri_prenotacao_prazo.py`; suspensão automática por processo segue nos itens de usucapião/retificação)* **Prorrogação/suspensão do prazo** da prenotação (TJMA 452, § 3º: dúvida, remessa ao juízo, editais e notificações, usucapião/retificação/adjudicação, saldo de emolumentos do art. 206-A, nova nota de exigências, reingresso) — `ri_protocolos.suscitacao_duvida` existe, mas o prazo corre sem suspender e a prenotação viva aparece como vencida (achado da revisão de 13/08; TJMA art. 48, IV).
- [ ] **P1** **Cancelamento das prenotações vencidas** (TJMA 452, caput e § 1º: cumprimento parcial não interrompe) — lista diária «a cancelar hoje» com registro do motivo.
- [ ] **P1** Alerta de **títulos contraditórios**: ao prenotar e ao lavrar, avisar se há prenotação **anterior aberta** na mesma matrícula (Lei 6.015, arts. 190–192; TJMA 447, § 2º) — hoje a amarração só liga protocolo ao ato.
- [ ] **P2** **Exame e cálculo** sem prenotação (TJMA 443 e 450: qualificação em 10 dias úteis; vedado em usucapião e adjudicação) — modalidade inexistente.
- [ ] **P2** **Cindibilidade do título** (TJMA 457): requerimento no protocolo, atos praticados × postergados e vedações (doação com reserva de usufruto, compra e venda com garantia real).
- [ ] **P2** **Desistência** com requerimento (firma, presença ou assinatura eletrônica) e devolução do depósito em até 5 dias úteis (TJMA 454–455).
- [ ] **P2** Cancelamento de ofício de prenotação indevida ou de outra circunscrição, com certidão do fato (TJMA 453).
- [ ] **P2** Distinguir **solicitante × apresentante** (TJMA 445–446: adquirente, credor, autor da penhora…) com sugestão pelo tipo de título.

**Eficiência**

- [ ] **P2** Natureza formal do título por lista (escritura pública / instrumento particular / título judicial + ato principal — TJMA 444, V).
- [ ] **P3** Leitura do código/QR do título eletrônico (SERP/ONR) para puxar apresentante e natureza.

**Adequação legal/doutrinária**

- [ ] **P1** **Encerramento diário do Livro 1** com o número de títulos protocolados e certificação do horário (TJMA 444, § 1º; 425, § 2º) — cruzar com `/nucleo/encerramento-diario`.
- [ ] **P1** Número de ordem **contínuo** entre livros da mesma espécie (TJMA 444, II) — confirmar que `UNIQUE(livro, numero)` com `livro='1A'` não reinicia ao abrir o 1-B.
- [ ] **P2** Campo «meio de apresentação» (balcão, SERP/ONR, correio) e aviso de que e-mail não protocola (TJMA 438).

## RI — Ficha do protocolo, comprovante e nota devolutiva (`/registro-imoveis/protocolo/<id>`, `/comprovante`, `/nota`, `/notas/<id>.odt`) — RX-07

**Apresentação/UI**

- [ ] **P2** Linha do tempo na ficha do protocolo: prenotação → nota(s) → reingresso → ato(s) → arquivamento/encerramento.
- [ ] **P3** «Comprovante» e «Nota devolutiva (.odt)» lado a lado, com o estado da nota (aberta / cumprida / fora do prazo).

**Funcionalidade**

- [ ] **P1** Comprovante com **alerta de cancelamento em 20 dias úteis** e data prevista de entrega ou de exigência (TJMA 447, § 4º, e 452, § 2º) — conferir o texto de `RI_PRENOTACAO` e de `/prenotacao/<id>/documento`.
- [ ] **P1** Nota devolutiva com exigências **de uma só vez**, claras, identificação e assinatura de quem emite (TJMA 451, § 1º) — `fundamentacao` hoje é opcional no esquema.
- [ ] **P2** **Nova nota de exigências** (TJMA 451, §§ 2º–4º): só após cumprimento integral da primeira, fundamentada, em 5 dias úteis — tipo e situação próprios.
- [ ] **P2** Reingresso registra os documentos recebidos e quem conferiu; «FORA_DO_PRAZO» oferece «novo protocolo» com os dados copiados.
- [ ] **P2** Reconsideração e **suscitação de dúvida** a partir da nota (TJMA 451, § 6º; Lei 6.015, arts. 198–204) — sem tela hoje.

**Adequação legal/doutrinária**

- [ ] **P2** Papel `PA-RI_NOTA` ainda **AB** na matriz de modelos — incluir nota devolutiva no seed e no comparativo com ato selado.
- [ ] **P3** Comentário de `ri_notas_devolutivas` cita «Código TJMA, art. 44» para o reingresso — atualizar para art. 452, § 3º, XIII (numeração do Código vigente).

## RI — Protocolo ↔ caixa (depósito prévio, recibo, saldo)

**Funcionalidade**

- [ ] **P1** Gravar `cx_protocolos.ri_protocolo_id` em toda prenotação — hoje, com a FK vazia, a ponte é o depósito prévio; protocolo unificado precisa do vínculo direto.
- [ ] **P1** **Saldo de emolumentos** (Lei 6.015, art. 206-A; TJMA 452, §§ 4º–6º): 5 dias úteis fora da contagem da prenotação; sem pagamento, devolução sem ato e cancelamento do protocolo — fluxo e aviso.
- [ ] **P2** Devolução de remanescente (TJMA 456) com recibo, para a conta de origem (454, § 3º).
- [ ] **P2** Recibo ao cliente sempre emitido na prenotação (pedido do balcão citado no código) — não depender de clique opcional.

**Eficiência**

- [ ] **P2** Orçamento a partir da natureza do título e cópia automática para o depósito prévio.

**Adequação legal/doutrinária**

- [ ] **P2** Emolumentos pela tabela **da data da prática do ato**, não da prenotação nem do depósito (TJMA 450, § 8º; CNN art. 188) — teste de virada de ano.

## RI — Lista de matrículas (`/registro-imoveis`) — RI-02

**Apresentação/UI**

- [ ] **P2** Colunas de situação: ativa/encerrada, ACERVO/ESTRUTURADA, CNM, conferida, digitalização, prenotação aberta.
- [ ] **P3** Filtros rápidos «sem digitalização», «sem CNM», «não conferidas» — dão forma aos backlogs medidos.

**Funcionalidade**

- [ ] **P2** Busca pelo número da transcrição de origem (livros anteriores a 1976), além de número e CNM.
- [ ] **P2** Teste de desempenho da lista paginada sem carregar teor (1.982 fichas / 31,8 MB de teor).

**Eficiência**

- [ ] **P3** Exportar a lista filtrada (CSV) para mutirões de conferência.

## RI — Ficha da matrícula (`/registro-imoveis/<id>`)

**Apresentação/UI**

- [ ] **P2** `ri_ficha.html` (~123 KB, dezenas de blocos condicionais) em abas: **Imóvel** · **Atos** · **Partes** · **Certidões** · **Prenotações** · **Digitalização** · **CNIB/ONR** · **Revisões**.
- [ ] **P2** Selo, QR e «quem praticou» visíveis em cada ato na tela, como no papel.
- [ ] **P3** Retirar `ri_ficha.html.bak_*` e `ri_nova.html.bak_*` da pasta `templates` — risco de editar o arquivo errado.

**Funcionalidade**

- [x] **P1** *(sandbox 3.6.195 — `ri_atos_cnib`; protocolo da Central obrigatório se `ri_cnib_exigir_protocolo_na_lavratura=1`)* **Consulta CNIB registrada na lavratura**: transmitente e adquirente consultados antes de alienação/oneração, com data, base e resultado gravados no ato (TJMA 506) — hoje a ficha só mostra a cópia local e nada fica no ato.
- [ ] **P1** Cópia CNIB com mais de 30 dias (`CNIB_DIAS_PARA_AVISAR`) pede confirmação escrita antes de lavrar alienação.
- [ ] **P2** «Conferida» (`ri_conferir`) mostra quem, quando e contra qual livro físico; revogação já auditada.
- [ ] **P2** Prenotações abertas da matrícula no topo da ficha (a certidão já traz a cláusula).

**Adequação legal/doutrinária**

- [ ] **P1** **Especialidade objetiva**: requisitos do art. 176, § 1º, II (identificação, medidas, confrontações; rural: CCIR, código INCRA/SIGEF, CAR) conferidos antes de selar a abertura (TJMA 459).
- [ ] **P2** **Especialidade subjetiva**: qualificação das partes do TJMA 479 (nome completo, estado civil, regime, CPF) — alerta quando `documento_valido=0`.

## RI — Abertura, edição, renumeração, encerramento e reabertura (`/nova`, `/editar`, `/renumerar`, `/parte-abertura`, `/selar-abertura`, `/encerrar`, `/reabrir`)

**Apresentação/UI**

- [ ] **P2** `ri_nova` em passos: origem (título, transcrição ou matrícula-mãe) → imóvel → proprietários → conferência.

**Funcionalidade**

- [ ] **P1** Abertura por **desmembramento, unificação ou destaque** vincula a matrícula-mãe e averba encerramento/remanescente na origem na mesma transação (Lei 6.015, arts. 233–235).
- [ ] **P1** Editar e renumerar exigem **motivo** e mostram diff antes/depois (cadastro muda; teor é imutável).
- [ ] **P2** Reabertura só com averbação que a justifique (auditoria `RI_MATRICULA_REABERTA` já existe).
- [ ] **P2** Encerramento por mudança de circunscrição grava a nova matrícula e o ofício, para as certidões citarem (TJMA 553, § 2º, e 559).

**Adequação legal/doutrinária**

- [ ] **P1** **Unitariedade da matrícula** (Gentil — um imóvel, uma matrícula): impedir segunda matrícula ativa com a mesma transcrição de origem ou o mesmo CNM.
- [ ] **P2** Selo e assinatura da abertura (`test_ri_assinatura_da_abertura`, `test_ri_selo_da_abertura`) no comparativo com ato selado (fase 3).

## RI — Lavratura de registro e averbação (`/<id>/atos`, `/preencher/<codigo>`, `/modelo/<codigo>`, minutas)

**Apresentação/UI**

- [ ] **P2** Mostrar o número que o ato terá **antes** de lavrar — inclusive na ficha ACERVO, que exige o número sem dizer qual é o certo.
- [ ] **P3** Seletor R/AV com exemplo de cada (hipoteca = R; cancelamento = AV).

**Funcionalidade**

- [ ] **P1** Ficha ACERVO: sugerir o próximo número lido do teor (`ri_numeros_do_teor.piso_do_proximo`) e recusar número já usado no texto (743 fichas).
- [ ] **P1** Validar **natureza × tipo do ato** contra `ri_naturezas` (código TJ) — impedir R para natureza de averbação e vice-versa.
- [ ] **P2** Protocolo digitado inexistente só gera aviso — oferecer a lista das prenotações abertas da matrícula para escolher.
- [ ] **P2** Minuta → ato separa **alienante × adquirente** (as 3.986 partes do acervo vieram todas como «proprietário»).

**Eficiência**

- [ ] **P2** Extrato eletrônico (Prov. CNJ 228/2026) como fonte do preenchimento guiado, quando o ONR publicar o formato.
- [ ] **P3** Usar ato anterior da mesma matrícula como base (ex.: AV de cancelamento a partir do R).

**Adequação legal/doutrinária**

- [ ] **P1** **Continuidade** (Lei 6.015, arts. 195 e 237): transmitente deve ser o titular ativo (`proprietario_ativo`) — alerta antes de lavrar aquisição derivada.
- [ ] **P1** Início do ato com **data e número do protocolo**; ato **datado e subscrito** por oficial, substituto ou escrevente autorizado (TJMA 443, § 1º, e 458) — validar no teor gerado.
- [ ] **P2** **Disponibilidade**: área transmitida ≤ área registrada, salvo aquisição originária (usucapião, título de domínio).

## RI — Rascunhos e «como ficará» (`/registro-imoveis/rascunhos`, `/<id>/como-ficara`) — RI-04

**Apresentação/UI**

- [ ] **P2** Lista com idade, autor e matrícula; destaque para rascunho com mais de 30 dias.

**Funcionalidade**

- [ ] **P2** Um rascunho por matrícula (`UNIQUE`) — mostrar quem está com o rascunho antes de sobrescrever.
- [ ] **P2** Impressão do «como ficará» mantém a marca de rascunho em todas as páginas (risco de parecer certidão, apontado no código) — teste de impressão.

**Eficiência**

- [ ] **P3** Levar o rascunho para minuta do Livro 3 quando o título mudar de livro (rota `livro3_minuta_do_rascunho` já existe — expor na tela do Livro 2).

**Adequação legal/doutrinária**

- [ ] **P2** Rascunho nunca serve de base a ficha ou certidão oficial — bloquear rota de papel sem a marca.

## RI — O que revisar antes de selar (`/registro-imoveis/revisoes`) — RI-05

**Apresentação/UI**

- [ ] **P2** Agrupar notas abertas por origem (IMPORTACAO / MANUAL / REVISAO) e por matrícula.

**Funcionalidade**

- [ ] **P1** Notas abertas exibidas **na tela do selo** — a nota não trava (decisão do módulo), mas quem sela precisa vê-la.
- [ ] **P2** Baixa (`/revisoes/<id>/baixar`) aceita USER — decidir se balcão pode baixar nota que o oficial abriu; exibir a decisão escrita na ficha.

**Adequação legal/doutrinária**

- [ ] **P2** Relatório para correição: notas baixadas no período, com a decisão escrita.

## RI — Selagem do ato (`/ato/<id>/selar`, `/selar-abertura`, `/selar-arquivamento`)

**Apresentação/UI**

- [ ] **P2** Prévia do carimbo (selo + QR + emolumentos) antes de confirmar.

**Funcionalidade**

- [ ] **P1** Fila «atos lavrados sem selo» (suspensos pelo selador) com ação reselar / cancelar com motivo — hoje só mensagem e auditoria `RI_ATO_SUSPENSO_SEM_SELO`.
- [ ] **P1** Multi-selo por ato (registro + arquivamento) conferido contra a tabela TJMA vigente e o código TJ da natureza.
- [ ] **P2** Base de cálculo em reais para o selador (conversão de centavos) — teste com valores altos e com isenção.

**Adequação legal/doutrinária**

- [ ] **P1** Não selar ato sem protocolo amarrado, salvo ato de ofício sinalizado (TJMA 443, § 1º).
- [ ] **P2** Alertar quando houver título arquivado e o selo 16.39 não for pedido.

## RI — Numeração dentro do teor (`/registro-imoveis/numeracao-no-teor`) — RI-06

**Apresentação/UI**

- [ ] **P2** As 13 fichas ESTRUTURADAS com teor à frente da tabela no topo (numerariam sozinhas); depois as ACERVO.

**Funcionalidade**

- [ ] **P2** Marcar ficha como «conferida contra o livro», com quem e quando.

**Adequação legal/doutrinária**

- [ ] **P1** Manter a regra de nunca criar `ri_atos` a partir do texto (teste) e listar fichas com salto ou repetição de número para conferência física.

## RI — Cancelamento de ato e atas de ocorrência (`/atos/<id>/cancelar`, `/atos/<id>/expurgar`, `/expurgos`) — RI-11

**Apresentação/UI**

- [ ] **P2** Explicar na tela a diferença entre **cancelamento** (averbação nova, fica na ficha) e **expurgo** (ata de ocorrência, só para ato de teste de implantação).

**Funcionalidade**

- [ ] **P1** Cancelamento de R (hipoteca, usufruto, penhora) marca `cancelado_por_ato_id` e sai da certidão de ônus — teste ponta a ponta.
- [ ] **P2** Ata `.odt` do expurgo no seed (amostra para conferência de layout).

**Adequação legal/doutrinária**

- [ ] **P2** Manter as travas do expurgo (só MANUAL, só o último ato, sem certidão nem remessa CTP/DOI, só ADMIN) cobertas por `test_ri_expurgo`.

## RI — Ficha da matrícula em papel (`/registro-imoveis/<id>/ficha.odt`) — RX-06

**Apresentação/UI**

- [ ] **P2** **RI-01**: a URL `.odt` devolve PDF conforme a preferência de impressão (`IMPW.resposta_do_papel`) — botão e nome do arquivo dizem o formato real, ou oferecer os dois.

**Funcionalidade**

- [ ] **P2** Opção «só atos vigentes» × «completa» (cancelados riscados).

**Adequação legal/doutrinária**

- [ ] **P1** Ficha ≠ certidão: rodapé «não vale como certidão» no `RI_FICHA` (paridade com a ficha do Livro 3).
- [ ] **P2** `RI_CABECALHO` idêntico em ficha, certidão, nota e recibo (o código diz que o timbre não pode divergir) — teste de igualdade.

## RI — Certidões da matrícula (`/registro-imoveis/certidoes`, `/<id>/certidao`, `/certidoes/<id>.odt`, `/cancelar`) — RI-03

**Apresentação/UI**

- [ ] **P2** Lista com filtros por tipo, período, requerente, situação (válida / vencida / cancelada) e selo.
- [ ] **P2** Explicar a fonte do inteiro teor (DIGITALIZAÇÃO × TEXTO) no formulário de emissão.

**Funcionalidade**

- [x] **P1** *(sandbox 3.6.195 — `ri_onus.py`; `test_ri_p1_revisao_194/195`)* **Certidão de ônus ignora atos «R»**: `contexto_ficha` filtra `a["tipo"] == "AV"` — hipoteca (art. 167, I, 2), servidão (I, 6), usufruto (I, 7), alienação fiduciária (I, 35), promessa de compra e venda e constrições lavradas como R ficam fora, e a certidão pode dizer «NADA CONSTA» sobre imóvel gravado. Incluir R restritivos não cancelados + teste de regressão.
- [x] **P1** *(sandbox 3.6.195 — natureza SAUIN primeiro; palavra-chave marca `conferir` e avisa na emissão)* Ônus detectados por **palavra-chave** no teor (`HIPOTEC`, `PENHOR`, `USUFRUT`…) — usar a natureza estruturada (`ri_naturezas`) e deixar os termos só como apoio; acrescentar cédula, arrolamento, bem de família, ação/citação, promessa, locação com vigência, sempre marcando para conferência humana.
- [ ] **P1** **Identificação segura** do requerente (nome + CPF/CNPJ) obrigatória e finalidade quando exigida (TJMA 548–551), com prontuário do pedido (552) e arquivamento cobrado (551, § 3º) — hoje `requerente`/`finalidade` são opcionais.
- [ ] **P1** Controle do **prazo de emissão**: inteiro teor digital em até **2 horas** (manuscrito até 5 dias) e download por 30 dias (TJMA 547) — `ri_certidoes` não guarda a hora do pedido.
- [ ] **P2** Matrícula **encerrada**: aviso antes de emitir e menção obrigatória; nova circunscrição citada (TJMA 553, §§ 2º–3º, e 559).
- [ ] **P2** Registrar a via: papel de segurança × eletrônica assinada ICP-Brasil (TJMA 553, § 1º).
- [ ] **P2** Cancelamento de certidão aceita USER — exigir motivo, selo cancelado no TJMA e perfil MANAGER/ADMIN (paridade RCPN/Protesto).

**Eficiência**

- [ ] **P2** Emitir em lote as certidões de um mesmo pedido (várias matrículas), cada uma com o seu selo (TJMA 555, § 2º).
- [ ] **P3** Segunda via da mesma certidão (mesmo hash) sem novo número.

**Adequação legal/doutrinária**

- [ ] **P1** **Lei 6.015, art. 21 / TJMA 553, § 4º**: alterações posteriores ao pedido e protocolos em tramitação — a cláusula de prenotações abertas existe (texto e reprodução); estender ao Livro 3.
- [ ] **P1** Livros anteriores à Lei 6.015 (transcrições): mencionar as circunstâncias que afetem a titularidade e a extensão do imóvel (TJMA 556).
- [ ] **P2** Validade de 30 dias impressa no molde (TJMA 553) — conferir `RI_CERTIDAO`.
- [ ] **P2** Seed com `ri_certidoes = 0` — papéis `PA-RI_CERTIDAO`, `_INTEIRO_TEOR`, `_ONUS`, `_PROPRIEDADE` ainda **AB** ([MODELOS-EMISSAO-PENDENTES](/cursor/stores/self/docs/revisao-modulos/MODELOS-EMISSAO-PENDENTES.md)); semear uma de cada tipo.

## RI — Espécies de certidão ausentes e pedidos eletrônicos

**Funcionalidade**

- [ ] **P1** Certidão **em resumo** e **em relatório por quesitos** (Lei 6.015, art. 19; TJMA 553) — hoje só inteiro teor, ônus e propriedade (`TIPOS_CERTIDAO`).
- [ ] **P1** Certidão **negativa de propriedade / busca por nome** pelo Indicador Pessoal (TJMA 549, III, e 555: resultado total, finalidade obrigatória) — o código diz que é «de outra tela», que não existe.
- [ ] **P1** Pedidos de certidão pela **plataforma SREI/ONR** — caminho `/v1/atendimento/eletronico` declarado em `onr_api.py` e desligado; verificação a cada hora exigida pelo TJMA 437.
- [ ] **P2** Certidão pelo **Indicador Real**, com os parâmetros da busca no texto e ressalva de matrícula/transcrição de descrição diversa (TJMA 554 e 557).
- [ ] **P2** Certidão de **ônus reais e ações reipersecutórias** (pedida nas escrituras), com ações conhecidas mesmo não averbadas (TJMA 558).
- [ ] **P2** Certidão de **transcrição** e de **documento arquivado** (TJMA 548, IV e VI).

**Adequação legal/doutrinária**

- [ ] **P1** Recusar certidões que reúnam dados pessoais de **mais de uma matrícula** (filiação de imóveis, propriedade com negativa de ônus e alienações — TJMA 550; LGPD).

## RI — Digitalização oficial da matrícula (`/<id>/digitalizacao`, `/arquivo`, `/miniatura`)

**Apresentação/UI**

- [ ] **P2** Data, SHA-256 e páginas do arquivo vigente na ficha, com histórico de versões.

**Funcionalidade**

- [ ] **P1** Backlog de `digi_path` vazio em 1.982/1.982 matrículas — painel de progresso com meta semanal, ligado a `MATRICULAS_SEM_IMAGEM_*` da documentação.
- [ ] **P2** Fila local «pendente de envio ao ONR» (marcada, sem transmissão) visível na tela do ONR/Next Cloud.

**Adequação legal/doutrinária**

- [ ] **P1** Etapas obrigatórias da digitalização (TJMA 435) como checklist no envio do arquivo.
- [ ] **P2** Teste: novo upload não altera certidão já emitida (snapshot em `pasta_snapshot_certidao`).

## RI — Fichas digitalizadas e imagens do disco (`/imagens/resolver`, `/imagens/do-disco`, `/imagens/copiar`) — RI-12

**Apresentação/UI**

- [ ] **P2** Resumo do diagnóstico banco × disco no topo (por causa: sufixo de página, pasta, maiúsculas) — já calculado em `ri_imagens.diagnostico()`.

**Funcionalidade**

- [ ] **P2** `ri_imagens_raiz` padrão `C:\ARPNET\C11\ONR\IMAGENS` — validar a pasta ao abrir e explicar como configurar.
- [ ] **P2** Separar acervo E-Ofício (`ri_imagens`) × digitalização oficial (`ri_digitalizacao`) nas telas — fontes diferentes, e a mistura põe página antiga em certidão.

**Eficiência**

- [ ] **P3** «Trazer do disco» em lote com prévia e desfazer.

## RI — Matrículas em Word (`/registro-imoveis/matriculas-doc`) — RI-13

**Apresentação/UI**

- [ ] **P2** Filtro e contagem por classificação (NOVA, SO_NO_DOC, AMBIGUA, AMPLIADA, IGUAL, DIVERGENTE, VAZIA).

**Funcionalidade**

- [ ] **P1** DIVERGENTE nunca sobrescreve o teor sem conferência contra o livro e registro de quem decidiu.
- [ ] **P2** AMPLIADA: carregar o Word com diff e aprovação do oficial, guardando a versão anterior do teor.

**Adequação legal/doutrinária**

- [ ] **P2** Gravar a origem do teor (Word / E-Ofício / lavrado aqui) para auditoria e para a certidão por texto de livro antigo (TJMA 556).

## RI — Importações do RI (`/registro-imoveis/importar`, `/importacoes`, `/importacoes/manual/<especie>`) — OP-07

**Funcionalidade**

- [ ] **P1** **OP-07 BLOCKED** (sem `.cgu`/seed): ensaio no sandbox com arquivo sintético de matrícula para fechar a fase C.
- [ ] **P2** Rejeitados (`ri_rejeitados`) exportáveis com motivo por linha.

**Adequação legal/doutrinária**

- [ ] **P2** Ato importado do acervo não entra em CTP/DOI retroativa sem dados completos (aviso já existe) — manter teste.

## RI — Usucapião extrajudicial (`/usucapiao`, ficha, peças, notificações, edital, decisão, registro) — US-01

**Apresentação/UI**

- [ ] **P2** Ficha do processo (`usucapiao_ficha`, ~24 KB) com etapa atual e próximos passos no topo; título de aba com o número.
- [ ] **P2** Lista com filtros por etapa, situação (EM_ANDAMENTO, SUSPENSO…) e prazo vencendo.

**Funcionalidade**

- [ ] **P1** Prenotação do requerimento **prorrogada até a decisão** (TJMA 452, § 3º, IV; item PRENOTACAO do checklist, art. 747) — ligar processo ↔ protocolo e suspender a contagem.
- [ ] **P1** Edital na **Central ONR** (`/ri/onr/edital/<id>`) com retorno do prazo — exercitar contra o simulador 8914.
- [ ] **P2** Registro do reconhecimento abre matrícula nova ou averba a existente conforme a área (igual / maior / menor / sem matrícula — TJMA 753, §§ 2º–4º, e 761).
- [ ] **P2** Modalidade **especial urbana coletiva** (Estatuto da Cidade, art. 10) ausente de `MODALIDADES`.

**Eficiência**

- [ ] **P2** Dossiê para qualificação externa (texto, CPF mascarado) com download e registro de quem recebeu.

**Adequação legal/doutrinária**

- [ ] **P1** Imóvel em garantia do SFH (TJMA 749, vedação absoluta) bloqueia o avanço de etapa — hoje é só item do checklist.
- [ ] **P2** Fundamento cita o **Prov. CNJ 149/2023**, que incorporou o Prov. 65/2017.

## RI — Usucapião: o que o Código de Normas exige (`/usucapiao/codigo-de-normas`) — US-02

**Apresentação/UI**

- [ ] **P2** Informar na página a versão/data do Código de Normas usado (Provimento TJMA 2026).

**Eficiência**

- [ ] **P3** Link de cada artigo para o item correspondente do checklist no processo aberto.

## RI — Retificação de área (`/registro-imoveis/retificacoes`) — RI-07

**Apresentação/UI**

- [ ] **P2** Grade de confrontantes com a resposta (ANUIU / SILÊNCIO / IMPUGNOU) e prazo de cada um.

**Funcionalidade**

- [ ] **P1** Prenotação prorrogada até a decisão (TJMA 452, § 3º, IV) — ligar processo ↔ protocolo.
- [ ] **P1** Averbação do resultado (`/averbacao`) atualiza área e medidas do cadastro da matrícula, não só o teor.
- [ ] **P2** Lista SIGEF «a vencer» (`sigef_a_vencer`) no painel do RI.

**Adequação legal/doutrinária**

- [ ] **P1** Impugnação fundamentada → tentativa de conciliação e remessa ao juízo (Lei 6.015, art. 213, § 6º) com peça própria.
- [ ] **P2** Análise do mosaico / SIG-RI antes do ato (TJMA 441) — não implementada.

## RI — Livro 3: registros (`/livro3`, `/livro3/novo`, `/livro3/<id>`, `/lancar`, `/importar-do-acervo`) — L3-01

**Apresentação/UI**

- [ ] **P2** Lista usa `atrib_lista.html` genérico — título e colunas próprias (natureza, CNM, vencimento, situação).

**Funcionalidade**

- [ ] **P1** Naturezas incompletas em `ra_registro.NATUREZAS`: faltam emissão de debêntures, penhor industrial/mercantil, cédula de crédito à exportação, cédula imobiliária rural e título registrado em inteiro teor (Lei 6.015, art. 178; TJMA 496 e 762–773).
- [ ] **P1** Cédula com hipoteca ou alienação fiduciária: lembrar o **registro da garantia na matrícula** (Livro 2) e ligar L3 ↔ matrícula.
- [ ] **P2** Vencimento das cédulas com alerta e cancelamento por quitação (averbação).

**Adequação legal/doutrinária**

- [ ] **P2** Teste de concorrência do contador único (`ri_numeracao`, livro '3') e da numeração contínua R-1, AV-2…

## RI — Livro 3: minutas, revisões e conferência (`/livro3/minutas`, `/livro3/revisoes`, `/livro3/conferir`) — L3-02 / L3-03 / L3-04

**Apresentação/UI**

- [ ] **P2** Minutas com número do registro, autor, idade e «como ficará».
- [ ] **P2** Conferência lado a lado: teor × miniatura da digitalização, com «conferido por».

**Funcionalidade**

- [ ] **P2** Ato devolvido à minuta (`/devolver-a-minuta`) exige motivo e preserva as partes (paridade com o Livro 2).
- [ ] **P2** Notas de revisão do Livro 3 visíveis na tela do selo (`/livro3/ato/<id>/selar`).

**Eficiência**

- [ ] **P2** «O que falta conferir» ordenado por prioridade (cédulas vigentes primeiro) e por lote de importação.

## RI — Livro 3: ficha `.odt` (`/livro3/<id>/ficha.odt`)

**Apresentação/UI**

- [ ] **P2** Mesma decisão de formato do RI-01 (ODT × PDF) para a ficha do Livro 3.
- [ ] **P3** «Fls. N/T» no cabeçalho de cada página.

**Adequação legal/doutrinária**

- [ ] **P2** Papel `PA-RI_LIVRO3_FICHA` ainda **AB** na matriz — registrar a amostra de revisão (241 KB, cabeçalho OK) e fechar a linha.

## RI — Livro 3: certidões (`/atribuicoes/certidoes`) — RI-08 / RI-21

**Apresentação/UI**

- [ ] **P1** Título «Certidões — Livro 3 (RI)» quando filtrado — tela compartilhada com RTD/RCPJ ([critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).

**Funcionalidade**

- [ ] **P1** **RI-08 / RI-21 BLOCKED**: seed sem `at_certidoes` do Livro 3 — semear registro L3 + certidão de inteiro teor para fechar a fase C e o papel `PA-RI_LIVRO3_CERTIDAO`.
- [ ] **P2** Emitir a partir da ficha do registro L3, com atos posteriores selecionados.

**Adequação legal/doutrinária**

- [ ] **P1** Certidão L3 com protocolos em tramitação (TJMA 553, § 4º) e prazo de 2 horas para inteiro teor digital (547 cita o registro no Livro 3).

## RI — Indicador Real — Livro 4 (`/registro-imoveis/indicador-real`) — RI-09

**Apresentação/UI**

- [ ] **P2** Colunas logradouro, bairro, rural/urbano e nº de proprietários ativos; paginação com total.

**Funcionalidade**

- [ ] **P2** Busca rural por CCIR, código INCRA/SIGEF, CAR e coordenadas (TJMA 554, parágrafo único).
- [ ] **P2** Origem de cada lançamento do Livro 4 (`RILANC`) visível; cancelamento já testado.

**Adequação legal/doutrinária**

- [ ] **P1** **LGPD**: busca fundada só no indicador exige identificação e finalidade (TJMA 549, III) — a rota não registra auditoria da consulta.

## RI — Indicador Pessoal — Livro 5 (`/registro-imoveis/indicador-pessoal`) — RI-10

**Apresentação/UI**

- [ ] **P2** Agrupamento por pessoa limitado a 60 resultados — paginação e aviso «há mais».

**Funcionalidade**

- [ ] **P1** 71% das partes sem CPF/CNPJ — fila de saneamento (cruzando teor e Word) antes da carga IPS/ONR.
- [ ] **P1** Cônjuges lançados no Indicador Pessoal (TJMA 431) — conferir que parte casada gera vínculo do cônjuge.
- [ ] **P2** Homônimos sem documento: mostrar a qualificação para desambiguar.

**Adequação legal/doutrinária**

- [ ] **P1** Registrar cada consulta nominal (quem, quando, finalidade) — LGPD e TJMA 549/552 (o titular pode pedir o prontuário).

## RI — CNIB — consulta (`/registro-imoveis/cnib`) — RI-CNIB-01

**Apresentação/UI**

- [ ] **P2** Idade da cópia local em destaque, com link para a atualização pela Central.

**Funcionalidade**

- [ ] **P1** Consulta pela **Central** (não só a cópia local) antes de alienação/oneração, com comprovante gravado (TJMA 506).
- [ ] **P2** Resultado com órgão e processo da ordem e botão «preparar averbação».

## RI — CNIB — o que espera seu okay (`/registro-imoveis/cnib/pendentes`) — RI-CNIB-02

**Apresentação/UI**

- [ ] **P2** Separar coincidência por CPF/CNPJ (forte) de coincidência só por nome (homônimo provável).

**Funcionalidade**

- [ ] **P1** Uma averbação **por proprietário atingido** (TJMA 504, parágrafo único) no preparo de `AV-INDISPONIBILIDADE`.
- [ ] **P2** Cancelamento de indisponibilidade pela ordem de cancelamento — modelo próprio (não está entre os 25).

**Adequação legal/doutrinária**

- [ ] **P2** Decisão «não é a mesma pessoa» com motivo, sem averbar, em relatório para correição.

## RI — CNIB — a cópia local e a Central (`/registro-imoveis/cnib/central`) — RI-CNIB-03

**Funcionalidade**

- [ ] **P1** Credencial CNIB ausente ou vencida vira mensagem de balcão (padrão `CredencialError`), nunca HTTP 500.
- [ ] **P2** Atualização periódica automática (robô) com leitura registrada (`ri_cnib_leituras`) e alerta acima de 30 dias.

**Eficiência**

- [ ] **P3** Ajustes (`/central/ajustes`) explicados na ajuda da tela.

## RI — ONR — índice real e editais (`/ri/onr`) — RI-ONR-01

**Apresentação/UI**

- [ ] **P2** Faixa fixa com ambiente (TESTES / HOMOLOG / PROD), base e estado da credencial (já calculados pela rota).
- [ ] **P2** Separar «enviado» × «aceito» × «recusado» com o motivo (`/envio/<id>/porque`).

**Funcionalidade**

- [ ] **P1** **Credencial ONR não configurada** — pacote de homologação `PACOTE_TESTE_ONR_52_PRONTAS` nunca enviado; instalar via `centrais_cred` e validar pelo botão «testar» (`/v1/auth/validacao`).
- [ ] **P1** Simulador **8914** estava OFF na última execução (WinError 10061) — subir e rodar o pacote 52 contra ele antes da homologação.
- [ ] **P2** `a_enviar` limitado a 100 — paginação e filtro pronto / pendente de endereço.
- [ ] **P2** Atualizar o indicador (PATCH `indicador_atualizar`) quando novo ato mudar dono ou descrição da matrícula.

**Adequação legal/doutrinária**

- [ ] **P1** Envio só com endereço conferido (teor → endereço → painel) e só ADMIN/MANAGER (`QUEM_ENVIA`) — manter teste.

## RI — ONR — endereços a conferir (`/ri/onr/enderecos`) — RI-ONR-02

**Apresentação/UI**

- [ ] **P2** Proposta mostra o trecho do teor de onde saiu o endereço e os campos CEP, logradouro, número, bairro, cidade e UF.

**Funcionalidade**

- [ ] **P1** Rodar o lote L1 (`tools/onr_lote_extrair_endereco_teor.py`) no PC — a fila tinha **1** proposta contra ~1.443 fichas pendentes.
- [ ] **P2** Painel de progresso da conferência (meta 50–100 por semana, fase L2).

**Adequação legal/doutrinária**

- [ ] **P2** AUDITOR não grava (comentário do menu) — manter teste de permissão em `test_onr_endereco_telas`.

## RI — Exportação ONR (`/registro-imoveis/onr`) — RI-ONR-03

**Apresentação/UI**

- [ ] **P2** Dizer na tela que gera arquivo para envio manual (não transmite) e por qual canal (IPS/Next Cloud × API).

**Funcionalidade**

- [ ] **P1** CNS padrão `000000` fixo no código (`get_setting("ri_cns", "000000")`, também no Next Cloud) — exigir configuração explícita; outra instalação exportaria o CNS desta casa.
- [ ] **P2** Linhas «sem documento» (`sem_doc`) listadas antes de gerar, com opção de bloquear.

**Adequação legal/doutrinária**

- [ ] **P2** `DTVENDA` = `DTREGAVERB` (10.781 de 10.781 nos envios anteriores) documentado na ajuda e coberto por teste.

## RI — Carga do Next Cloud SAS (`/registro-imoveis/onr/next-cloud-sas`) — RI-ONR-04

**Apresentação/UI**

- [ ] **P2** Quadro de prontidão (matrículas sem imagem, 50 primeiras) exportável em CSV.

**Funcionalidade**

- [ ] **P2** Formulário de adesão pré-preenchido só com conta Google e CNS configurados (validar antes de mostrar).
- [ ] **P2** XML da carga completa do Indicador Pessoal só depois de mostrar os vínculos sem documento (conferência já calculada).

## RI — Integração ONR/SAEC — estado atual × ideal

**Funcionalidade**

- [ ] **P1** **Protocolo eletrônico**: caminhos `/v1/protocolo*` declarados e **desligados** — títulos do SERP/ONR não entram no Livro 1 pelo sistema; o TJMA 437 exige verificar a plataforma a cada hora.
- [ ] **P2** **Edital de leilão** (alienação fiduciária, `/v1/edital/leilao`) e intimação para consolidação — não ligados.
- [ ] **P2** **Cobrança ONR** (`/v1/cobranca*`) — decidir se a casa usa; se sim, integrar ao caixa.
- [ ] **P2** Timeout e retentativas (`PRAZO_PADRAO=60`, 2 tentativas) medidos em homologação; erro de rede explicado ao balcão.
- [ ] **P2** `test_onr_carga` (18 passed, suíte interrompida por árvore alterada) — rerodar com o servidor parado.

**Adequação legal/doutrinária**

- [ ] **P1** Regularização fundiária: dados no SAEC (TJMA 138-A) e inventário estatístico IERI-e (TJMA 427-A) — não implementados.
- [ ] **P2** Extrato eletrônico (Prov. CNJ 228/2026) e SERP «Meu Registro» (Prov. 229/2026) — ler a íntegra antes de programar.

## RI — Modelos de atos (`/registro-imoveis/modelos-atos`) — RI-14

**Apresentação/UI**

- [ ] **P2** Catálogo com busca por natureza, fundamento (art. 167) e tipo R/AV, e prévia com os campos destacados.

**Funcionalidade**

- [ ] **P1** Só **25 modelos** — faltam os do «Grupo A» da revisão de 13/08: promessa de compra e venda e cessão, servidão, cessão de direitos hereditários, dação em pagamento, bem de família, locação com vigência, consolidação fiduciária, cancelamento de indisponibilidade/penhora, união estável, ação real/averbação premonitória, demolição, desapropriação, resultado de retificação, legitimação fundiária/de posse, CDRU/CUEM, comodato, tombamento e pagamento por serviços ambientais (art. 167 com a Lei 14.382/2022; TJMA 496 e 532).
- [ ] **P2** `pendencias()` listar os `[CAMPO]` não preenchidos na mensagem que impede a lavratura.

**Adequação legal/doutrinária**

- [ ] **P2** `R-TITULO-DOMINIO`: «sob condições resolutivas» só quando houver cláusula (achado de 13/08, ainda não confirmado como corrigido).
- [ ] **P2** Conferir **um a um** (não por amostragem) os incisos do art. 167 citados nos 25 modelos.

## RI — Modelos de documento do RI e papéis (`/modelos` aba RI, `/registro-imoveis/modelos`, `/ri/modelos`) — MO-01 / RI-20

**Apresentação/UI**

- [ ] **P2** Três portas para modelos RI (`/modelos`, `/registro-imoveis/modelos` sobre `ri_modelos` legado com zero linhas, e `/ri/modelos`) — manter uma e redirecionar as outras.

**Funcionalidade**

- [ ] **P1** Validar o modelo ao salvar (renderização restrita) — hoje o erro só aparece na emissão («O modelo da ficha tem um erro»).
- [ ] **P2** Prévia de cada papel RI com a matrícula #1 — **8 de 10** papéis RI ainda **AB**.
- [ ] **P2** «Voltar ao padrão» com diff do ajuste da casa.

**Adequação legal/doutrinária**

- [ ] **P2** Governança de «salvar para todos» × ajuste local (paridade Notas/Protesto), com autor e data.

## RI — Selos e emolumentos (`/registro-imoveis/selos`) — RI-15

**Apresentação/UI**

- [ ] **P2** Totais por período, natureza e escrevente; exportação CSV/ODS.

**Funcionalidade**

- [ ] **P1** Valores lidos do **texto do selo por regex** (`_valores`: «Total R$ … Emol R$ …») — gravar emolumentos e total estruturados no ato (`ri_atos.emolumentos` é TEXT) e usar o texto só como apoio.
- [ ] **P2** Selos de certidão, prenotação e Livro 3 no mesmo livro de selos.

**Adequação legal/doutrinária**

- [ ] **P1** Colunas do livro de selos/emolumentos conforme os livros administrativos obrigatórios (TJMA 188–208).

## RI — CTP — prefeituras (`/registro-imoveis/ctp`) — RI-16

**Funcionalidade**

- [ ] **P1** `tipoServico`/`tipoAto` registrais não publicados (padrão «Notarial» no `ri_ctp.py`) — confirmar com a CENSEC antes da primeira remessa.
- [ ] **P2** Código IBGE padrão (`2198765`, Cidade Exemplo) fixo no módulo — mover para configuração da serventia.
- [ ] **P2** Registrar protocolo/recibo da CENSEC na remessa fechada (o envio é manual).

**Eficiência**

- [ ] **P2** Pendências por ato (ex.: «imóvel rural sem código do INCRA») com atalho direto para completar.

## RI — DOI — Receita Federal (`/registro-imoveis/doi`) — RI-17

**Funcionalidade**

- [ ] **P1** Toda competência sem ato com **declaração negativa** e recibo (cobrança AUDITUS na correição) — conferir que nenhum mês some.
- [ ] **P2** Resolver as «dúvidas» de alienante/adquirente (`NDOI.lados_das_partes`) antes de gerar.

**Eficiência**

- [ ] **P2** Prazo (último dia útil do mês seguinte) em alerta no painel e em Obrigações recorrentes.

**Adequação legal/doutrinária**

- [ ] **P2** Mesmo dado da CTP (`ri_ctp_itens`) — a tela mostra a origem e impede divergência entre as duas remessas.

## RI — Obrigações periódicas ainda não cobertas

**Funcionalidade**

- [ ] **P1** **SINTER/CIB** (IN RFB 2.275/2025): demais municípios a partir de **janeiro de 2027** — compartilhar os dados da operação logo após o ato.
- [ ] **P1** Comunicação **mensal ao INCRA** das modificações em imóveis rurais (TJMA 434, § 4º, «a»).
- [ ] **P1** **Livro de aquisições por estrangeiros** + relatório trimestral a INCRA, Corregedoria e MAPA (TJMA 424, VI, e 621–629; Lei 5.709/71).
- [ ] **P2** **DOITU → SPU** mensal (TJMA 434, § 4º, «d»).
- [ ] **P2** **SISCOAF** quando couber (TJMA 434, § 4º, «h»; pendência de correição já semeada em `inspection_seed`).
- [ ] **P2** Relação permanente de **ações reais e reipersecutórias** (TJMA 434, § 4º, «g»).
- [ ] **P2** **Adjudicação compulsória extrajudicial** como procedimento com decisão fundamentada (Lei 6.015, art. 216-B; TJMA 703–715) — hoje só o modelo `R-ADJUDICACAO`.
- [ ] **P2** **Consolidação da propriedade fiduciária** e leilões (Lei 9.514, arts. 26–27; TJMA 716–728-A; prazos em dias úteis — 436, § 1º).

## RI — Delegatários (`/registro-imoveis/delegatarios`) — RI-18

**Apresentação/UI**

- [ ] **P2** Períodos «por confirmar» destacados e título de aba próprio (template sem `block title`).

**Funcionalidade**

- [ ] **P1** Rota aceita **USER** para criar e confirmar períodos — é daqui que sai o nome de quem praticou os atos antigos na ficha; restringir a ADMIN/MANAGER com motivo.
- [ ] **P2** `SUGESTAO_DELEGATARIOS` com nomes fixos no código — mover para dado de instalação.

**Adequação legal/doutrinária**

- [ ] **P2** Validar lacunas e sobreposições de períodos (ato sem responsável sai sem fecho — mostrar quantos atos ficam assim).

## RI — Numeração das matrículas (`/registro-imoveis/numeracao`) — RI-19

**Apresentação/UI**

- [ ] **P2** Linhas cruas por volume (2, 2A…2S) recolhidas por padrão; a série vem primeiro (já).

**Funcionalidade**

- [ ] **P1** USER pode **fixar o próximo número** da série — restringir a ADMIN/MANAGER; salto de numeração exige motivo e fica como lacuna auditável.
- [ ] **P2** Tela «aplicar CNM em lote» nas matrículas em branco (`ri_cnm` confere 1.656/1.656 — TJMA 428, IV; Prov. CNJ 143/2023).

**Adequação legal/doutrinária**

- [ ] **P2** Conferência com o Livro 2 físico após cada importação (OP-07).

## RI — Teoria registral transversal (teor, cabeçalho, assinaturas, selos)

**Funcionalidade**

- [ ] **P1** **Teor sem lacunas**: nenhum `[CAMPO]`, `XXX` ou `{{ }}` residual em ato, ficha ou certidão — validação na lavratura e na emissão (achado `R-USUCAPIAO` de 13/08).
- [ ] **P2** Verificação da corrente de hash (`hash_ato` / `hash_anterior`) por matrícula, integrada a `/integridade`.

**Apresentação/UI**

- [ ] **P1** **Cabeçalho único** (brasão, ofício, CNS, cidade) em ficha, certidão, nota devolutiva, comprovante e recibo; ficha do Livro 2 com a mesma grade da ficha do Livro 3 (3.6.193).
- [ ] **P1** **Selo e QR** legíveis em cada ato e certidão impressos — comparativo com ato selado ([CHECKLIST-COMPARATIVO-SELADO](/cursor/stores/self/docs/revisao-modulos/CHECKLIST-COMPARATIVO-SELADO.md), linhas 4–9).

**Adequação legal/doutrinária**

- [ ] **P1** **Assinatura e fecho**: ato subscrito com nome e função (TJMA 458); ato do acervo com o delegatário do período (RI-18); certidão com fecho e assinatura; ficha sem «dou fé».
- [ ] **P2** **Registro × averbação** (Gentil): atos constitutivos/translativos no art. 167, I; alterações e extinções no art. 167, II — ajuda e validação pela natureza.
- [ ] **P2** **Concentração na matrícula** (Lei 13.097/2015, arts. 54–58): averbações premonitórias, ações e constrições refletidas na certidão (TJMA 558).
- [ ] **P2** **Rogação**: ato de ofício sinalizado como tal (sem protocolo) e com fundamento.

**Eficiência**

- [ ] **P3** Relatório das fichas do acervo ainda pendentes de limpeza de teor (`ri_teor_limpo`, aplicada só com aprovação do oficial).

## RI — Testes, seed e sandbox

**Funcionalidade**

- [ ] **P1** Seed sandbox com certidões RI (IT, ônus, propriedade), nota devolutiva, registro L3 + certidão L3 e um processo de usucapião e de retificação — destrava RI-08, RI-21 e os papéis RI **AB**.
- [x] **P2** *(sandbox 3.6.195)* Teste de regressão: certidão de ônus com hipoteca e usufruto lavrados como R.
- [ ] **P2** Testes de prorrogação da prenotação (dúvida) e do alerta de título contraditório.
- [ ] **P2** Testes de papel (roles) nas rotas escondidas pelo menu (Exportação ONR, Next Cloud, imagens, delegatários, numeração).

**Eficiência**

- [ ] **P3** Retirar `test_ri_lavrar_teor.py.bak_pre_unifica_protocolo` e demais `.bak` da árvore de testes.

---

# Visão geral — painel da serventia

Módulo **Atalhos → Visão geral**. Rota `/` (`dashboard` em `app.py`); template `dashboard.html`; KPIs via `database.dashboard_stats(alert_days)`; bloco **Atos em andamento** via `inacabados.resumo` (medição na hora, sem lista paralela). Menu lateral e atalhos em `base.html` filtrados por `user.role`. Revisão sandbox **TR-01** ([00-transversal](/cursor/stores/self/docs/revisao-modulos/00-transversal.md), [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)); inventário [modulos-inventario-urls](/cursor/stores/self/internal/modulos-inventario-urls.md).

**Fluxo esperado:** login → painel como primeira tela → leitura de KPIs (tarefas/expedientes/Malote) e filas prioritárias → «Atos em andamento» (atribuições) antes do administrativo → aprofundar via links ou menu (somente rotas permitidas ao perfil).

---

## Visão geral — Painel geral (`/`) — TR-01

**Apresentação/UI**

- [ ] **P1** Reduzir competição visual entre faixa SANDBOX, cabeçalho cartorial e «Painel geral» — primeiro conteúdo útil acima da dobra (T-02; [critica-telas-sandbox](/cursor/stores/self/docs/critica-telas-sandbox.md)).
- [ ] **P2** Cards KPI vazios («Nenhuma pendência») com **atalho** para criar tarefa ou expediente a partir do empty state.
- [x] **P3** Título de aba e `<h1>` «Painel geral» coerentes (`dashboard.html`; smoke TR-01).
- [ ] **P2** Aviso crítico de inspeção sem data-base (`stats.inspection_without_start`) com link evidente para Inspeções/configuração de ciência.

**Funcionalidade**

- [x] **P1** Bloco **Atos em andamento** (`inacabados`) listado **antes** de tarefas/expedientes, ordenado por parados e volume (relato #29; falha explícita em `andamento_erro`).
- [ ] **P2** KPIs «Vencidas / Vencem em N dias / Tarefas abertas / Expedientes ativos / Aguardando terceiro» **consistentes** com `/tarefas` e `/expedientes` (T-03; régua `TP.condicao_aberta`).
- [ ] **P2** Card «Fora das vistas» (`tarefas_fora_do_vocabulario`) com texto e caminho para corrigir situação na lista de tarefas.
- [ ] **P2** Links «Atos parados» preservam filtro `so_parados` e fonte (`inacabados_lista`).
- [ ] **P3** Indicadores auxiliares (`implantacao_abertas`, disputas de escrita) só quando > 0, sem poluir o painel.

**Eficiência**

- [ ] **P2** Atalhos contextuais no painel para filas críticas (ex.: vencidas, expedientes prontos a encerrar) conforme perfil.
- [ ] **P2** Rótulo «Vencem em N dias» reflete `alert_days` das configurações (não hardcode divergente).
- [ ] **P3** «Ver todas» / «ver todos» mantêm filtros úteis (prioridade, setor) quando aplicável.

**Adequação legal/doutrinária**

- [ ] **P1** Painel exibe apenas **agregados** (contagens, tipos de ato, setores) — **sem** CPF, nome completo ou endereço de partes em KPIs/tabelas resumo (LGPD; sigilo do acervo).
- [ ] **P2** Alertas de inspeção/prazo interno não substituem prazo legal do ato — copy de aviso operacional, não certidão.

## Visão geral — Menu, atalhos e perfis (role-gating)

**Apresentação/UI**

- [ ] **P2** «Visão geral» no menu lateral com estado `atual` em `/` e marca «Início» visível após login.
- [ ] **P2** Nome da unidade truncado no sidebar — tooltip ou expansão (crítica global).

**Funcionalidade**

- [ ] **P1** Rota `/` protegida por `@login_required`; pós-login redireciona ao painel; anônimo não vê KPIs.
- [ ] **P1** Itens de menu condicionados a `user.role` (ADMIN/MANAGER/USER/AUDITOR) — escrevente não vê blocos administrativos ([modulos-inventario-urls](/cursor/stores/self/internal/modulos-inventario-urls.md)).
- [ ] **P2** Perfil **AUDITOR**: painel e Malote consultivos, sem ações destrutivas expostas por widget.
- [ ] **P3** Busca/acordeão/mobile do menu não esconde «Visão geral».

**Adequação legal/doutrinária**

- [ ] **P1** **Menor privilégio:** URLs ADMIN-only retornam 403/redirect mesmo se descobertas manualmente — widgets do painel não vazam rotas proibidas.

## Visão geral — Malote, Livros e transversal

**Funcionalidade**

- [ ] **P2** Badge «Malote» / `global_stats.overdue` coerente com card «Vencidas» do painel ([Malote — transversal](#malote--transversal-menu-painel-integrações)).
- [ ] **P2** Tabelas «Pendências prioritárias» e «Expedientes em andamento» batem com listagens Malote (ML-*).
- [ ] **P2** Mensagem «dias sem encerrar» (Livros) não contradiz widgets do painel ([Livros — transversal](#livros-e-acervo--transversal-menu-notas-ri-auditoria)).

**Eficiência**

- [ ] **P3** Atalho direto do painel para `/expedientes/prontos-para-encerrar` quando houver fila.

**Adequação legal/doutrinária**

- [ ] **P2** Navegação a partir do painel permanece auditável (`audit_logs`) quando passar a existir ação POST no painel — hoje GET-only OK.

---

# Esqueleto — demais módulos (a detalhar)

Preencher nas próximas fatias do checklist. Submódulos conforme menu (`base.html` / inventário 2026-09-24).

## Visão geral

*(Detalhado na seção [Visão geral — painel da serventia](#visão-geral--painel-da-serventia) acima.)*

## Tabelionato de Notas

*(Detalhado na seção [Notas — Tabelionato de Notas](#notas--tabelionato-de-notas) acima.)*


## Registro de Imóveis

*(Detalhado na seção [Registro de Imóveis (RI)](#registro-de-imóveis-ri) acima.)*

## Protesto

*(Detalhado na seção [Protesto — cartório de protesto (Lei 9.492/97)](#protesto--cartório-de-protesto-lei-949297) acima.)*


## Registro Civil das Pessoas Naturais (RCPN)

*(Detalhado na seção [RCPN — Registro Civil das Pessoas Naturais (Livro I)](#rcpn--registro-civil-das-pessoas-naturais-livro-i) acima.)*

## Operação — Livros e acervo

*(Detalhado na seção [Livros e acervo — núcleo, numeração e cargas](#livros-e-acervo--núcleo-numeração-e-cargas) acima.)*

## Operação — Malote

*(Detalhado na seção [Malote — Expedientes, tarefas e inspeções](#malote--expedientes-tarefas-e-inspeções) acima.)*

## Gestão — Administrativo

- **Dinheiro:** Caixa · Protocolo geral · Protocolos parados · Depósito prévio · Recibos · Emolumentos · Selos emitidos
- **Atendimento:** Senhas · WhatsApp · Robôs · Inacabados · Rascunhos · Fraudes · Relatórios
- **A casa:** Fraudes · Checklists · Recorrências · LGPD · TI · Auditoria · Integridade
- **Ajuda:** Consulta · Problemas · Projeto · Base · Agente
- **Configuração:** Modelos · Caixa · Selador · Rede · Usuários · Acervo corrigir · Importações · Atualizações · Configurações

---

## Contagem (itens `- [ ]` por bloco detalhado)

| Bloco | Itens pendentes (`- [ ]`) |
|--------|---------------------------|
| RTD | 61 |
| RCPJ | 31 |
| Transversal RCPJ/RTD | 33 |
| **Total RTD/RCPJ (primeira fatia)** | **125** |
| RCPN | 138 |
| Malote | 40 |
| Livros e acervo | 100 |
| Notas | 76 |
| Protesto | 61 |
| RI | 265 |
| Visão geral | 24 |
| **Total parcial (RTD + RCPJ + transversal + RCPN + Malote + Livros + Notas + Protesto + RI + Visão geral)** | **829** |

*(Itens `- [x]` nas seções «Concluído na 3.6.193» e «RI — Concluído na 3.6.193» (9 itens RI) não entram na contagem de pendências.)*

---

## Sincronização deste arquivo

- **Canônico (desenvolvimento):** `SANDBOX\sistema\DOCUMENTACAO\CHECKLIST_MELHORIAS_DESENVOLVIMENTO.md`
- **Espelho INSTALAR:** `SERVIDOR\INSTALAR_CARTORIO_GESTAO\DOCUMENTACAO\` (mesmo nome)
- **Project store:** `/cursor/stores/self/docs/CHECKLIST_MELHORIAS_DESENVOLVIMENTO.md`

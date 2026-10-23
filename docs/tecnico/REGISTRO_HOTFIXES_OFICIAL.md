### HOTFIX-2026-10-13-05 - RI: dispensa de CIB por matrícula (settings.cib_dispensado_matriculas) - ESPELHADO_SBX (LIVE)

- **Quem/pedido:** agente (Grok Bot), escrevente 13/10/2026 15:25: abrir a matrícula 4022 (derivada do encerramento da 1196) sem CIB.
- **Exigência:** `ri_web.py` `_exige_cib` + `_cib_valido` em `ri_nova_matricula` (abertura) e `ri_editar_matricula` (edição) para imóvel rural fora do acervo. Não havia exceção. O envelope do selo de abertura (`ato_selado.envelope_da_abertura_da_matricula`) não usa CIB.
- **Mudança:** `_cib_dispensado(numero, settings.cib_dispensado_matriculas)` nos dois pontos; campo continua opcional. Gravado `cib_dispensado_matriculas = ["4022"]`; auditoria RI_CIB_DISPENSADO com o motivo.
- **Aplicado sobre o PF (16FC687F6F9F → 90ACFB430AEC)**, import conferido antes; SANDBOX/INSTALAR patch sobre as próprias versões (com ri_onus_ia de outro agente). Backup PF `ri_web.py.bak-hf1305-20261013-153758`.
- **Antes/depois:** /saude 3.6.290 / 3.6.290 (15:41:17 RESULTADO OK). Teste `tmp/enc1311/hf5/test_hf1305.py` OK.
- **Desfazer:** apagar a chave ou restaurar o .bak + reiniciar.
- **Status:** ESPELHADO_SBX.

### HOTFIX-2026-10-13-04 - Comprovante de gratuidade: incluir selos anteriores ao «desde», um a um (mat. 4019 → FERJ) - ESPELHADO_SBX (LIVE)

- **Quem/pedido:** agente (Grok Bot), escrevente 13/10/2026 14:37 («pendência de envio de comprovante de isenção» da 4019).
- **Mudança:** `gratuidade_comprovante.py` - `incluidos()` lê `settings.gratuidade_comprovante_incluir` (ids de sd_selos); `pendentes()` passa a listar também esses, mesmo antes de `gratuidade_comprovante_desde`. Gravado `gratuidade_comprovante_incluir = 26461,26463,26464,26465` (abertura, R-01, AV-02 e arquivamento da 4019), com auditoria SETTING_ALTERADA.
- **Antes/depois:** /saude 3.6.290 / 3.6.290 (14:42:22 RESULTADO OK). Backup PF `gratuidade_comprovante.py.bak-hf1304-20261013-144121`.
- **Teste:** `tmp/enc1311/hf4/test_hf1304.py` TESTE_HF1304_OK; tela /gratuidades/comprovantes (beatriz) lista os 4 selos.
- **Desfazer:** apagar a chave (lista some) ou restaurar o .bak + reiniciar.
- **Status:** ESPELHADO_SBX.

### HOTFIX-2026-10-13-03 - Selo RI: «Os nomes das partes devem ser informados» em ato sem partes (de ofício) - ESPELHADO_SBX (LIVE)

- **Quem/pedido:** agente (Grok Bot), AV-08/1196 (ri_atos 3778) recusado 13/10/2026 14:02.
- **Causa:** `parteAto: []` - encerramento de ofício não tem partes em ri_partes.
- **Correção (ri_web.py):** `_partes_para_o_selo_ri()` - partes do ato; senão proprietários ativos da matrícula; senão partes do último ato da matrícula com partes; senão a serventia (unit_name + serventia_cnpj). Usado no selo do ato RI e no arquivamento RI. No 3778 vai «UNIÃO FEDERAL» (partes do AV-7).
- **INCIDENTE 14:08-14:13:** a 1ª cópia (14:05) levou o ri_web.py do INSTALAR, que já tinha mudança NÃO publicada de outro agente (`import ri_onus_ia`, módulo ausente em PF) → app não subia. Restaurado `ri_web.py.bak-hf1303-20261013-140530` (14:13:25 OK). Reaplicado sobre a versão PF (6AA6C235460A → 16FC687F6F9F) às 14:15:59 OK.
- **Teste:** `tmp/enc1311/hf3/hf3_test.py` (rota de selar com banco mínimo e selador MOCK, sem TJ) TESTE_HF1303_OK.
- **Atenção:** SANDBOX e INSTALAR ri_web.py contêm a mudança `ri_onus_ia` de outro agente + este patch; não publicar o INSTALAR em PF sem o módulo `ri_onus_ia.py`.
- **Desfazer:** restaurar `ri_web.py.bak-hf1303b-20261013-141510` + reiniciar_servidor.ps1.
- **Status:** ESPELHADO_SBX. /saude 3.6.290.

### HOTFIX-2026-10-13-02 - Selo RI: campo «protocolo» vazio recusado pelo TJMA (ato de ofício) - ESPELHADO_SBX (LIVE)

- **Quem/pedido:** agente (Grok Bot), AV-08/1196 (ri_atos 3778) recusado 13/10/2026 13:51:55 e 13:53:59: «O tamanho do campo "protocolo" deve estar entre 1 e 50».
- **Causa:** `ato_selado.envelope_do_ato_do_ri` (e abertura/prenotação) enviava `"protocolo": ""` quando o ato não tem prenotação (encerramento de ofício). Nenhum selo gerado (sd_selos sem linha para o ato).
- **Correção:** `protocolo_para_o_tj()`: vazio → «DE OFICIO»; acima de 50 caracteres → corta em 50. Só `ato_selado.py`.
- **Antes/depois:** /saude 3.6.290 / 3.6.290 (13:59:07 RESULTADO OK). Backup PF `ato_selado.py.bak-hf1302-20261013-135803`; SANDBOX/INSTALAR `*.bak-hf1302-*`.
- **Teste:** `tmp/enc1311/hf2/test_hf1302.py` (envelope com mock, sem TJ) TESTE_HF1302_OK.
- **Como desfazer:** restaurar o .bak e `installer\reiniciar_servidor.ps1 -Acao Reiniciar`.
- **Status:** ESPELHADO_SBX.

### HOTFIX-2026-10-13-01 - Revisão IA consultiva (revisao_previa_modo) + rascunho do formulário de lavrar RI - ESPELHADO_SBX (LIVE)

- **Quem/pedido:** agente (Grok Bot), pedido da escrevente 13/10/2026 11:27/11:32 («modo revisão IA está atrapalhando»; recusa não pode descartar o formulário).
- **Antes:** /saude 3.6.290. **Depois:** /saude 3.6.290 (11:38:07 RESULTADO OK).
- **Causa do travamento:** sem revisão do texto EXATO (hash) a lavratura era recusada; 3 recusas no AV-8/1196 em 13/10 (10:54, 11:03, 11:21), e falsos positivos repetidos (livro 2-F x «Livro 2 – Registro Geral», selo/emolumentos ausentes no teor, numeração livro físico x digitalização, tipo R/AV do formulário, remanescente em encerramento).
- **O que mudou:** `revisao_previa.py` - `settings.revisao_previa_modo` ('consultivo' padrão; 'bloqueante' = regra antiga). Consultivo: MANAGER/ADMIN e ato de ofício (encerra=1, isento, motivo de isenção) lavram sem revisão/lendo; GRAVE pede só o clique «Prosseguir mesmo assim» (`revisao_prosseguir`); demais usuários aproveitam a revisão anterior automaticamente com texto ≥80% igual; prompt com a lista de falsos positivos. `ri_web.py` passa contexto/prosseguir e audita REVISAO_PREVIA_CONSULTIVA. `templates/_revisao_previa.html` checkbox Prosseguir. `templates/ri_ficha.html` rascunho localStorage do formulário de lavrar, restaurado quando a página volta com recusa. «Selar este ato» não passa pela revisão (sem mudança).
- **Teste:** `tmp/enc1311/hf/test_hf1301.py` (sbx e pf) TESTE_HF1301_OK; compilação OK.
- **Arquivos/backup:** PF `*.bak-hf1301-20261013-113724`; SANDBOX/INSTALAR `*.bak-hf1301-20261013-*`.
- **Como desfazer:** `revisao_previa_modo=bloqueante` (sem reinício) ou restaurar os .bak e `installer\reiniciar_servidor.ps1 -Acao Reiniciar`.
- **Status:** ESPELHADO_SBX (sandbox recebeu o patch sobre sua própria versão; serviço :8899 não reiniciado).

### HOTFIX-2026-10-09-08 - RI: não oferecer «Selar este ato» como pendência para ato que já tem selo (razão, teor ou acervo anterior ao sistema) - «Selar mesmo assim» só ADMIN/MANAGER com confirmação

- **Data/hora:** 2026-10-09; SANDBOX ~16:00 (reiniciado :8899, /saude 200), INSTALAR 16:09, Program Files 16:09:05-16:09:30 (America/Sao_Paulo).
- **Quem:** agente (Grok Bot), continuação do HOTFIX-2026-10-09-07 (pedido da escrevente 09/10 13:55), para evitar selo em duplicidade no acervo.
- **Versão em produção:** 3.6.288 antes e depois (sem bump); /saude 8765 e 8899 = 200 3.6.288; = INSTALAR VERSAO.txt. Id conferido no registro canônico (09-01 a 09-07 em uso).
- **Regra (`motivo_ja_selado`, ri_web.py):** ato sem `selo_texto` NÃO é pendência quando (1) tem selo ligado em sd_selos não cancelado (inclusive CONSULTA PÚBLICA TJMA) -> «Já selado (acervo)»; (2) o teor (sem tags) cita código de selo `[A-Z]{6}000000[A-Z0-9]{14,18}` ou «Selo Geral» -> «Selo citado no teor»; (3) ato de acervo (acervo=1 ou origem ≠ MANUAL, importado do sistema anterior) -> «Já selado (acervo)».
- **Mudança:** ficha mostra a etiqueta; o formulário de selar some para escrevente (USER) e vira «Selar mesmo assim» para ADMIN/MANAGER, com aviso de duplicidade e caixa de confirmação obrigatória; aviso da ficha encerrada e atalho da lista de matrículas ignoram esses atos (SQL: acervo=0, sem sd_selos, teor sem código/«SELO GERAL»); `ri_selar_ato` recusa no servidor sem papel ADMIN/MANAGER + `confirmar_ressele=1`, e audita RI_ATO_RESSELE_CONFIRMADO quando confirmado. Ato novo (MANUAL, acervo=0) sem selo continua normal.
- **Efeito no LIVE (contagem só leitura):** 1.250 atos deixaram de aparecer como pendentes (953 acervo, 147 selo no teor, 150 selo no razão); restam 0 atos sem selo de fato. 3769 AV-1..AV-9 e 1196 AV-1..AV-7 viraram etiqueta (inclusive AV-6/1196, que é ato de acervo e-Ofício de 16/04/2026 — critério 3).
- **Paths:** ri_web.py; templates/ri_ficha.html; tests/test_ri_ressele_acervo.py (novo). ri_matriculas.html sem mudança.
- **Hashes (Program Files = SANDBOX/sistema = INSTALAR, sha256/12):** ri_web.py 34D29DA7A0AD (antes 8776200C6EFB); templates/ri_ficha.html 51BB813A2E7F (antes 42CC363B68EE).
- **Testes direcionados:** test_ri_ressele_acervo 3 passed; test_ri_selar_no_encerramento 5 passed; test_ri_selar_ato + test_ri_encerrar_pelo_formulario 28 passed (193 s). Sem bateria completa.
- **Serviço:** cópia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar` 16:09:05-16:09:30 RESULTADO OK.
- **Backup:** Program Files `*.bak-ressele-20261009-160905`; SANDBOX/INSTALAR `*.bak-ressele-20261009`.
- **Como desfazer:** (elevado) restaurar os dois `*.bak-ressele-20261009-160905` + reiniciar_servidor.ps1; SANDBOX/INSTALAR restaurar `*.bak-ressele-20261009`.
- **Selagem:** nenhuma. Robô não sela.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado.**
- **nota_dev:** HOTFIX_OFICIAL: RI - ato do acervo / com selo no razão ou no teor não aparece como pendência de selo; «Selar mesmo assim» só ADMIN/MANAGER com confirmação.

### HOTFIX-2026-10-09-07 - RI: «Selar este ato» onde há encerramento (item + arquivamento c/ folhas + gratuito/isento + REURB-S/E/misto) e atalho na ficha encerrada e na lista de matrículas

- **Data/hora:** 2026-10-09; SANDBOX 15:4x (reiniciado :8899, /saude 200), INSTALAR 15:46, Program Files 15:47:31-15:48:01 (America/Sao_Paulo).
- **Quem:** agente (Grok Bot). Pedido da escrevente (Tabeliã e Registradora Substituta, MANAGER) em 09/10/2026 13:55: «verifique na matrícula 1130, 1196 ... no campo de matrículas onde tem encerramento, insira o campo de selar o ato, tanto pra selar o item quanto o de arquivamento e a opção de gratuito ... inclusive a informação de gratuito pelo REURB».
- **Versão em produção:** 3.6.288 antes e depois (sem bump). /saude 8765 e 8899 = 200 3.6.288 antes e depois; = INSTALAR VERSAO.txt.
- **Id:** conferido no registro canônico (Downloads\CartorioGestao\DOCUMENTACAO): 09-01 a 09-06 em uso; este é o 09-07. OBS: nas cópias SANDBOX/INSTALAR/Program Files do registro há uma entrada «09-06 RI carimbo selo antigo (TJMA)» que NÃO está no canônico, onde o 09-06 é o RCPN «Selar novamente» — colisão de id anterior, só registrada aqui, não renumerada.
- **Mudança (mínima):**
  - `templates/ri_ficha.html`: o formulário «Selar este ato» (ato lavrado sem selo, inclusive com a ficha encerrada) ganha «Modalidade REURB» (S marca isento e preenche o motivo da Lei 13.465/2017; E e misto seguem cobrados), «Selar também o arquivamento (16.39)» + folhas; item sugerido 16.22.2 quando o ato é de encerramento e não tem item; id `selar-ato-<id>` por ato; aviso na ficha encerrada com atalho «Selar AV-xx» para cada ato MANUAL sem selo (ADMIN/MANAGER/USER); script que abre o selar pelo `#selar-ato-<id>`.
  - `templates/ri_matriculas.html`: na lista/cadastro de matrículas, selo «Encerrada» e botão «Selar <ato>» quando há ato lavrado aqui sem selo.
  - `ri_web.py`: `ri_selar_ato` sela o arquivamento logo depois do selo do ato (mesmo caminho de `ri_selar_arquivamento`, mesma gratuidade; falha não desfaz o selo do ato); se o selo do ato não sai, avisa que o arquivamento não foi pedido; consulta da lista ganha `ato_sem_selo`/`ato_sem_selo_rotulo`. REURB no servidor já vinha de `ler_isencao_do_form` (reurb_tipo=S => isento + motivo).
  - O formulário de lavrar/encerrar (HOTFIX-2026-10-08-08) já tinha item, arquivamento, gratuito e REURB — conferido, não alterado.
- **Paths:** ri_web.py; templates/ri_ficha.html; templates/ri_matriculas.html; tests/test_ri_selar_no_encerramento.py (novo).
- **Hashes (Program Files = SANDBOX/sistema = INSTALAR, sha256/12):** ri_web.py 8776200C6EFB (antes C1201B346C95); templates/ri_ficha.html 42CC363B68EE (antes B9EE1AF88686); templates/ri_matriculas.html D1C6B4EE67E2 (antes B2BEE9E8DFBF).
- **Testes (direcionados, sem bateria completa):** árvore de ensaio 32 passed (test_ri_selar_ato + encerrar_pelo_formulario + novo); SANDBOX 10 passed (test_ri_selar_no_encerramento + test_ri_encerrar_pelo_formulario), 178 s.
- **Serviço:** cópia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar` 15:47:31-15:48:01 RESULTADO OK; /saude 3.6.288. (Uma 1ª tentativa às 15:46:40 abortou antes de copiar — erro no script de deploy, alias `H` — e fez rollback + um reinício extra; nada foi alterado nela.)
- **Backup:** Program Files `*.bak-selarenc-20261009-154731`; SANDBOX e INSTALAR `*.bak-selarenc-20261009`.
- **Selagem:** NENHUMA. Robô não sela (regra 05/10); nenhum selo gerado, TJ não chamado.
- **Dados (mesmo pedido, antes deste código):** AV-08/1196 (ato 3776, sem selo: selo_texto NULL, nada em sd_selos) expurgado pelo caminho do sistema `ri_expurgo.expurgar` em 09/10 14:33:49 (ri_expurgos id 1; auditorias 28933 RI_ATO_EXPURGADO e 28934 RI_MATRICULA_ENCERRAMENTO_DESFEITO); 1196 reaberta (ATIVA, encerrada=0, sem data/motivo); próximo ato sugerido AV-8. Backup do banco: ProgramData\CartorioGestao\backups_saneamento\cancelar_enc_1196_20261009\cartorio_gestao_antes_20261009-142253.sqlite3.
- **Como desfazer:** (elevado) restaurar os três `*.bak-selarenc-20261009-154731` em Program Files e `installer\reiniciar_servidor.ps1 -Acao Reiniciar`; no SANDBOX/INSTALAR restaurar `*.bak-selarenc-20261009`.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado.**
- **nota_dev:** HOTFIX_OFICIAL: RI - «Selar este ato» no encerramento com item, arquivamento (folhas), gratuito e REURB; atalho na ficha encerrada e na lista de matrículas.

### HOTFIX-2026-10-09-06 - RI: carimbo dos atos do acervo com o selo antigo (texto oficial consultado no TJMA) — rótulo por prefixo e hora HH:MM

- **Data/hora:** 2026-10-09, dados 12:03 e 12:20–12:21; código 12:16 (SANDBOX), 12:18 (Program Files). America/Sao_Paulo.
- **Quem:** agente (Grok Bot). Pedido da escrevente (oficial substituta) em 09/10/2026 11:55: «Pode consultar cada selo antigo no TJ e gravar o texto completo para sair o carimbo com extenso e QR.»
- **Versão em produção:** 3.6.288 (hotfix sem bump). /saude ok antes e depois (8765 e 8899).
- **Dados (sem alterar ato, teor nem selo; nenhuma chamada de selagem):**
  - Consulta pública `GET https://selo.tjma.jus.br/portal-selo/portal-cidadao/selos/<código>/imovel`, com 1,5 s entre os pedidos, feita do SERVIDOR.
  - Só grava quando o `codSelo` é idêntico, o CNS é 000000 (CIDADE EXEMPLO), o selo não está cancelado e, no escopo 3, quando a matrícula no TJ é a do ato e a data fica a até 45 dias do ato.
  - Fica tudo em INSERTs em `sd_selos` (tabela='ri_atos', ato_id, referencia `tjma-consulta-publica:idSelo=…`, obtido_por «CONSULTA PÚBLICA TJMA 09/10/2026 (autorizada pela escrevente)»).
  - 168 selos em 152 atos, nas auditorias SD_SELO_TEXTO_TJ_GRAVADO 28900 (12 selos: os atos de 18/08 e a mat. 1196) e 28903–28906 (156 selos do acervo).
  - A auditoria 28900 traz a marca «HOTFIX-2026-10-09-03/selos-tj», posta antes de conferir os ids. O id certo é este, 09-06, e o log não foi alterado.
  - Backups:
    - `C:\ProgramData\CartorioGestao\backups_saneamento\selos_tj_20261009\cartorio_gestao_antes_20261009-120227.sqlite3`;
    - `…\selos_tj_20261009\e3\cartorio_gestao_antes_20261009-122030.sqlite3`.
  - Para reverter: `DELETE FROM sd_selos WHERE obtido_por LIKE 'CONSULTA PÚBLICA TJMA 09/10/2026%'`.
- **Código (mínimo):**
  - `ri_web.py`: nova `selos_do_ato_rotulados(tipo, etiquetas)`. Com vários selos ligados ao ato, PRENOT sai como «SELO DE PRENOTAÇÃO» e vem primeiro; ARQUIV e MATRIC ganham o rótulo próprio; os demais saem como «SELO DE REGISTRO/AVERBAÇÃO». Vale para os 3 desenhos do carimbo (tela, ODT, HTML).
  - `selo.py`: `ler_texto` aceita hora sem segundos (o portal do TJ informa só HH:MM). Nenhum segundo foi inventado.
  - `tests/test_selos_antigos_tj.py`: 3 testes novos.
- **Hashes (sha256/12), iguais em Program Files, INSTALAR e SANDBOX:**
  - ri_web.py C1201B346C95 (antes 316F6ABD09BF);
  - selo.py 4E63AA6456EF (antes 8AB49DD095BD);
  - tests/test_selos_antigos_tj.py 943BA554461D.
- **Testes** (cópia leve):
  - test_selos_antigos_tj: 3 passed.
  - Relacionados: test_ri_carimbo_igual_em_todos tem 5 failed, que JÁ FALHAM no código anterior (base: 196 passed, 5 failed).
- **Serviço:**
  - SANDBOX :8899 reiniciado com `rodar.py --derrubar` (relançado pelo loop) às 12:16.
  - Produção: cópia elevada (backup `*.bak-selostj-20261009-121744`) + `installer\reiniciar_servidor.ps1 -Acao Reiniciar`, RESULTADO OK às 12:18.
- **Pendências para conferência humana:** ver `tmp\selos_tj_20261009\relatorio` / `/workspace/relatorio_selos_antigos_tj.txt`, que lista os códigos não encontrados, a matrícula ou a data divergente, os sem matrícula no TJ, o cancelado AV-3/4011 e o Selo Geral 27417124 (físico).
- **ESPELHADO_SBX:** sim. **LIVE:** aplicado.

### HOTFIX-2026-10-09-02 - RCPN: folha do REGISTRO DE NASCIMENTO - URL do selo dentro da caixa + linhas de assinatura (declarante e quem lavrou)

- **Data/hora:** 2026-10-09 09:10 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot - Robo Modelos/Fidelidade), pedido da escrevente escrevente (users.id 6) via Robo escrevente; caso real termo 19579, Livro 24, Folha 193 (assento 8371, PESSOA EXEMPLO). **Aplicacao e reinicio autorizados pelo usuario neste chat em 09/10/2026 ~09:09** ("Sim, aplica o hotfix na producao e reinicia o :8765 agora").
- **Versao em producao:** 3.6.288 (antes e depois; sem bump). /saude = INSTALAR VERSAO.txt = 3.6.288. Sem entradas ABERTO antes.
- **Causa:** (1) a URL de consulta do selo (`https://selo.tjma.jus.br/#/resumo/REGNAS...`, `ri_odt.carimbo_compacto_html` l. 1486-1489) e uma palavra so e o template `rcpn_folha_impressa.html` (l. 166, `.carimbo-do-selo`) nao tinha regra de quebra: invadia a coluna de Notas. (2) a folha nao tinha linhas de assinatura.
- **Mudanca:** `templates/rcpn_folha_impressa.html`: CSS `.carimbo-do-selo` (URL 8pt, `overflow-wrap:anywhere; word-break:break-all`; QR e codigo intactos) + bloco `face.assinaturas` depois do carimbo. `atribuicoes_web.py`: nova `_assinaturas_da_folha(con, assento)` (so NASCIMENTO; declarante = rc_pessoas papel DECLARANTE; quem lavrou = rc_atos REGISTRO criado_por -> RCETQ.nome_de_quem_lavrou/funcao_de_quem_lavrou; dado ausente = branco; erro = linhas em branco) passada nas duas rotas da folha (`/rcpn/<id>/folha` e `/folha/papel` PDF/ODT) e no ODT editavel. Template compartilhado com casamento/obito: para eles a lista vem vazia (folha igual). Nenhum dado de ato/selo alterado; sem schema.
- **Paths:** templates/rcpn_folha_impressa.html, atribuicoes_web.py
- **Hashes:** template A9AA5962FEDE73A8 -> 1193F49FFD0C543F (prod = INSTALAR = SANDBOX); atribuicoes_web.py B88DA6E2622893E1 -> 095F52F766C360BE (prod = INSTALAR; o SANDBOX tem os mesmos blocos + as mudancas ja existentes dos Modelos, hash 8712E911EA5D93CA).
- **Backup:** Program Files e INSTALAR `*.bak_pre_hotfix_selo_assinaturas_20261009`; SANDBOX `*.bak_pre_selo_margem_20261009`.
- **Servico:** copia elevada (UAC) + `installer\reiniciar_servidor.ps1 -Acao Reiniciar` 09/10 09:10:09-09:10:19 -> RESULTADO OK; novo processo na 8765 PID 41760 (inicio 09:10:17); /saude 200 3.6.288. Log: SANDBOX/tmp/selo_margem_20261009/aplicar_producao.log.
- **Validacao:** /rcpn/8371/folha responde 302 -> /login sem sessao (sem 500). Conferencia offline com o banco em mode=ro e o template de producao: "PESSOA EXEMPLO, Declarante" e "escrevente, Escrevente Autorizada"; URL do selo REGNAS000000YAGQMNVGI8T80C30 dentro da caixa (producao_19579_conferencia.pdf). Testes sandbox: 22 passed (tests/test_folha_nascimento_selo_e_assinaturas.py novo + test_rc_folha_tela + test_termo_novo_impressao).
- **Status:** ESPELHADO_SBX (SANDBOX/sistema e INSTALAR com os mesmos blocos; template com hash igual). **LIVE aplicado.**
- **nota_dev:** HOTFIX_OFICIAL: folha do nascimento - URL do selo quebra dentro da caixa; linhas de assinatura do declarante e de quem lavrou, nomes do ato. (sem chamado Ajuda aberto - registrado aqui)
- **Como verificar:** logado, abrir http://127.0.0.1:8765/rcpn/8371/folha (so leitura) e imprimir pelo navegador (Ctrl+P, retrato).
- **Como desfazer:** copiar de volta os dois `*.bak_pre_hotfix_selo_assinaturas_20261009` (elevado) e `installer\reiniciar_servidor.ps1 -Acao Reiniciar`.

### HOTFIX-2026-10-08-08 - RI: «Encerrar matrícula» passa a abrir o formulário «Lavrar ato» (texto editável com modelo, selo com item, gratuidade, arquivamento, revisão com IA)

- **Data/hora:** 2026-10-08 14:46 (v1) e 14:59 (v2, natureza por modelo), America/Sao_Paulo.
- **Quem:** agente (Grok Bot). Pedido da escrevente (oficial substituta) em 08/10/2026 14:23, depois de encerrar a mat. 1196 pela aba antiga.
- **Versão em produção:** 3.6.288 (hotfix sem bump). /saude ok antes (14:29:56 e 14:46:12) e depois (14:46:57 e 14:59:48).
- **Problema:** a aba «Encerrar esta matrícula» lavrava sozinha uma averbação com teor automático de duas linhas («ENCERRAMENTO DESTA MATRÍCULA. MOTIVO: … O imóvel passa a constar da(s) matrícula(s) …»). Não dava para escrever nem conferir o texto, não pedia selo, item nem gratuidade, e todo encerramento saía igual. Foi assim que nasceu a AV-08/1196 de 14:17:57; o teor foi corrigido no mesmo dia, de ofício, com o texto da escrevente (audit 28680).
- **O que mudou (mínimo seguro: reaproveita o formulário de lavrar, que já encerra no mesmo passo sem segunda averbação):**
  - `templates/ri_ficha.html`:
    - O painel «Encerrar esta matrícula» não tem mais formulário próprio. Ficou um botão «Encerrar matrícula — abrir o formulário do ato», que abre `?lavrar=1&encerrar=1#novo-ato`.
    - Com `enc_pre`, o formulário de lavrar abre com:
      - aviso no topo e seletor «Modelo de encerramento», com 5 modelos: mudança da técnica de escrituração, desmembramento, unificação, transferência de circunscrição e texto livre;
      - tipo AV;
      - número sugerido (`piso.proximo`; editável na ficha de acervo);
      - natureza do modelo, que é o título que a ficha imprime;
      - teor do modelo, editável, com a prévia de sempre;
      - «Este ato encerra a matrícula?» aberto e marcado, com o motivo preenchido e o destino;
      - selo com item da tabela, gratuidade com motivo, arquivamento opcional e revisão com IA/«suprido», tudo como já existia no lavrar.
    - «Selar este ato» abre com a gratuidade e o motivo já gravados no ato (antes vinha sempre desmarcada).
  - `ri_web.py`:
    - funções novas `modelos_de_encerramento` e `MARCA_A_PREENCHER` (módulo), e `_pre_encerramento` (só ADMIN/MANAGER e só com a ficha aberta);
    - `ri_ficha` passa `enc_pre` e abre o formulário;
    - `ri_lavrar_ato` recusa o teor que ainda tenha «PREENCHER…», antes de tomar número ou pedir selo.
    - A rota POST `/encerrar` FICA (usada por «Voltar a encerrar» e pelos testes), só não é mais oferecida para o encerramento novo.
  - `static/ri_encerramento.js` (novo):
    - troca o modelo, perguntando antes se o texto já foi editado;
    - leva a matrícula de destino para o trecho «PREENCHER: … matrícula» do texto;
    - não deixa enviar enquanto sobrar «PREENCHER».
  - `tests/test_ri_encerrar_pelo_formulario.py`: 5 testes novos.
- **Hashes (sha256/12), iguais em Program Files, INSTALAR e SANDBOX:**
  - ri_web.py 63AAC22D045E (antes 362EAAD93A91);
  - templates/ri_ficha.html B9EE1AF88686 (antes CB4A92AF8971);
  - static/ri_encerramento.js 1440892914DD (novo);
  - tests/test_ri_encerrar_pelo_formulario.py C1E14A0A588D.
- **Testes** (cópia leve, timeout, sem a bateria completa):
  - test_ri_encerrar_pelo_formulario + test_ri_encerrar_pelo_ato + test_ri_reabrir_matricula + test_relato_66_etiqueta_do_selo: 30 passed, 1 failed.
    - A falha é `test_ri_reabrir_matricula::test_quem_atende_nao_reabre`, que JÁ FALHA no código anterior. Conferido com os arquivos originais: 1 failed. A rota reabrir aceita USER; não é deste hotfix.
  - v2: test_ri_encerrar_pelo_formulario + test_ri_encerrar_pelo_ato: 16 passed.
- **Serviço:**
  - SANDBOX :8899 reiniciado com `rodar.py --derrubar` + `rodar.py` às 14:45 e às 14:58.
  - Produção: cópia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar`, RESULTADO OK. PID 11556 (v1), depois 24712 (v2).
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files). **LIVE aplicado.**
- **Backup:**
  - Program Files: `*.bak-encform-20261008-144612` (original) e `*.bak-encform2-20261008-145900` (v1).
  - SANDBOX/INSTALAR: `*.bak-encform-20261008`.
  - CartorioGestao/tmp/enc1196_20261008/{pf_orig, pf_v1, sbx_before, ins_before}.
  - Script idempotente: `payload2/aplicar_enc_form.py`.
- **nota_dev:** HOTFIX_OFICIAL: encerrar matrícula = lavrar ato (formulário único com modelo editável, selo/gratuidade/arquivamento/revisão IA, encerra no mesmo passo); recusa «PREENCHER»; selar ato traz a gratuidade gravada.
- **Sem selar. Sem alteração de schema.**
- **Saneamento de dados no mesmo pedido** (fora do código; audits 28680 e o seguinte, RI_NATUREZA_AJUSTADA_SANEAMENTO), na mat. 1196, ato 3776 (AV-08):
  - teor trocado pelo texto exato da escrevente;
  - hash recalculado (é o último ato da ficha);
  - item 16.22.2 + isento + motivo gravados para o «Selar este ato»;
  - natureza = título do teor;
  - motivo do encerramento com remissão à Mat. 4.022.
  - Backup: ProgramData/CartorioGestao/backups_saneamento/enc1196_20261008/.
  - O SELO NÃO FOI GERADO (regra permanente do oficial de 05/10/2026, `selo_robo`: robô não sela).

### HOTFIX-2026-10-08-07 - Revisão com IA: «Já verificado/suprido» por apontamento, «Prosseguir mesmo assim» e lavrar com a revisão anterior (gerente)

- **Data/hora:** 2026-10-08 ~13:09 (America/Sao_Paulo).
- **Quem:** agente (Grok Bot), pedido da escrevente (oficial substituta) neste chat em 08/10/2026 12:31. Ela não conseguia lavrar o AV-8/1196 (encerramento com transposição para a Mat. 4.022) por causa da revisão com IA.
- **Versão em produção:** 3.6.288 (antes e depois; hotfix sem bump). /saude 12:37:34 e 13:09:49 = 3.6.288 ok.
- **Causa do bloqueio:** a revisão nº 36 (0 grave, 3 de atenção) liberava o texto EXATO revisado, e atenção nunca bloqueou. Mas a trava compara o hash do texto: qualquer mudança (mesmo uma vírgula, ou um F5 que recarrega o texto) exige nova revisão. A recusa ia só para o flash, sem auditoria, e a tela não dizia que atenção não bloqueia. Por isso parecia que os avisos impediam a lavratura. A Mat. 4.022 inexistente NÃO bloqueia: o destino do encerramento é texto livre.
- **Mudanças:**
  - `revisao_previa.py`:
    - `exigir_para_lavrar` conta só os GRAVES **pendentes** (os supridos não contam). Novos parâmetros opcionais: papel, usar_revisao_anterior, justificativa_anterior, texto_atual, tipo.
    - Gerente ou administrador pode «lavrar com a revisão anterior» quando o texto ficou ≥ 90% igual (difflib), é do mesmo tipo, não tem GRAVE pendente e há justificativa de pelo menos 10 letras. Fica gravado em `resultado_json.liberacoes` e a função devolve «anterior:<id>:<semelhança>».
    - Funções novas: `suprir`, `anotar_supridos`, `graves_pendentes`, `chave_do_achado`/`mesmo_assunto`, `_revisao_anterior`, `_anotar_liberacao`.
    - A marca «suprido» fica no próprio `resultado_json`; não há tabela nova nem mudança de schema.
    - Marca herdada: vale nas revisões seguintes do mesmo ato quando o assunto é o mesmo (raízes das palavras do «o_que»). No RI vale só depois do último ato lavrado da matrícula. Atenção suprida não cobre GRAVE.
  - `revisao_previa_web.py`: nova rota POST `/revisao-previa/<id>/suprir`.
    - Perfis ADMIN, MANAGER e USER; GRAVE só ADMIN/MANAGER, com observação de pelo menos 10 letras.
    - Grava auditoria `REVISAO_PREVIA_SUPRIDO` por item.
    - As rotas de andamento e de «última revisão» devolvem `suprido` por achado e `graves_pendentes`.
  - `static/revisao_previa.js`:
    - Cada achado ganha a caixa «Já verificado/suprido», o campo de observação e o botão «Marcar selecionados como supridos». Achado já marcado aparece «✔ Já verificado/suprido por X em dd/mm».
    - Sem GRAVE pendente aparece a faixa verde «Nada impede a lavratura. Os avisos de «atenção» não bloqueiam» e o botão «Prosseguir mesmo assim», que leva ao botão de lavrar sem enviar nada.
    - Editar o teor depois da revisão mostra o aviso «O texto mudou depois da revisão».
  - `templates/_revisao_previa.html`: data-suprir-url e data-pode-suprir-grave; texto de ajuda; quadro do gerente «Lavrar com a revisão anterior» (revisao_usar_anterior + revisao_justificativa_anterior).
  - `ri_web.py` (ri_lavrar_ato) e `notas_web.py` (lançar):
    - passam papel, texto e tipo à trava;
    - auditam `REVISAO_PREVIA_ANTERIOR_USADA`;
    - o RI audita a recusa como `RI_LAVRAR_RECUSADO_REVISAO`, para o bloqueio deixar rastro.
  - `tests/test_revisao_suprido.py`: 10 testes novos.
- **Paths:** revisao_previa.py, revisao_previa_web.py, static/revisao_previa.js, templates/_revisao_previa.html, ri_web.py, notas_web.py, tests/test_revisao_suprido.py.
- **Hashes (sha256/12):**
  - Iguais nas três árvores: _revisao_previa.html DFFBEB1C3512; ri_web.py 362EAAD93A91 (antes DFDFBC8D24B8); notas_web.py 1623E9C52611 (antes 2D20FA67D362); _revisao_previa.html antes 24B71E4D5129; tests/test_revisao_suprido.py ADB33163E11E.
  - revisao_previa.py, revisao_previa_web.py e revisao_previa.js já DIVERGIAM antes deste hotfix: os anexos da revisão de 07/10 estão em SANDBOX/INSTALAR e não em produção. O patch foi aplicado nas duas linhagens, preservando essa diferença.
    - Program Files: 743E2C1F91E5 / 950D06BDD0C2 / 011E53A56C1C (antes B3CF0D0D4746 / EE7E7C6C514A / A0C3535E18F6).
    - SANDBOX = INSTALAR: AC545D03D405 / 9990181134A1 / C06602CE29A6 (antes 490684F5AF63 / 8FB609DAD6E0 / 22F7220AD162).
- **Testes:** feitos com timeout, numa cópia leve da árvore do sandbox. A suíte completa não foi rodada.
  - test_revisao_suprido (10 testes novos) + test_revisao_previa: 22 passed em 58 s na linhagem SANDBOX/INSTALAR.
  - Os mesmos testes com os 3 arquivos da linhagem de produção: 22 passed em 110 s.
  - A regressão ampliada (6 arquivos), e depois o test_ri_encerrar_pelo_ato sozinho, passaram do timeout porque outros agentes deixaram o SERVIDOR com CPU em 100% (pytest e tar deles). Não houve falha.
- **Serviço:**
  - Sandbox :8899 reiniciado com `rodar.py --derrubar` + `rodar.py` (~13:00); GET /revisao-previa/1/suprir respondeu 405, ou seja, a rota existe.
  - Produção: cópia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar`, RESULTADO OK (13:08:52–13:09:49); PID 29776.
- **Validação em produção (só leitura):**
  - /revisao-previa/1/suprir = 405; o JS servido tem «Prosseguir mesmo assim».
  - Revisão 36 (AV-8/1196): graves_pendentes = 0; a trava libera o texto revisado.
  - Com o texto mudado, a recusa já oferece ao gerente a revisão anterior; para +1 frase, a semelhança é 0,996.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR; Program Files com o mesmo patch na linhagem de produção). **LIVE aplicado.**
- **Backup:** CartorioGestao/tmp/hotfix_suprido_20261008/{pf_before_deploy, sbx_before, ins_before}; Program Files `*.bak-suprido-20261008-130852`; SANDBOX `*.bak-suprido-20261008`; INSTALAR em ins_before. Script idempotente `payload/aplicar_suprido.py` (marcador HOTFIX-2026-10-08-07).
- **nota_dev:** HOTFIX_OFICIAL: revisão com IA - «já verificado/suprido» por apontamento (GRAVE só gerente, com observação), marca herdada no mesmo ato, «Prosseguir mesmo assim», lavrar com a revisão anterior (gerente, ≥90%, justificativa) e auditoria da recusa.
- **Sem selar. Sem lavrar. Sem alteração de schema.** Não houve gravação no banco além do que a tela faz.

### HOTFIX-2026-10-08-06 - RCPN: certidão de casamento imprime o regime por extenso (não o código COMUNHAO_PARCIAL)

- **Data/hora:** 2026-10-08 ~10:55 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot), pedido da oficial neste chat em 08/10/2026 ~10:40 («corrigir comunhão parcial de bens»). O termo já saía certo pelo HOTFIX-2026-10-08-04; a certidão ainda mostrava o código.
- **Versão em produção:** 3.6.288 (antes e depois; hotfix sem bump). /saude = VERSAO.txt = INSTALAR = sandbox :8899 = 3.6.288.
- **Causa:** `rc_certidao.montar_teor` e `rc_certidao_quadro._quadro_casamento` (HTML/ODT via `@regimebens`) imprimiam `rc_assentos.regime_bens` cru. A tela de lavrar/habilitação grava o CÓDIGO de `hc_schema.REGIMES` («COMUNHAO_PARCIAL»).
- **Mudanças:**
  - `rc_certidao.py`: novo `regime_da_certidao` — chama `regime_por_extenso` de `rc_modelos_do_livro` (mesma tabela do termo) e, se traduziu, sobe para maiúsculas («COMUNHÃO PARCIAL DE BENS»), como o acervo grava; texto livre passa como veio. Usado na linha «REGIME DE BENS DO CASAMENTO».
  - `rc_certidao_quadro.py`: `quadro["regime"]` passa por `RCE.regime_da_certidao` (HTML impresso + ODT).
- **Paths:** rc_certidao.py, rc_certidao_quadro.py
- **Hashes (prod = SANDBOX/sistema = INSTALAR):** rc_certidao.py b5a8372f4c66 (antes 63ac6dece6c5); rc_certidao_quadro.py 397e7a9eed93 (antes 57235e810109).
- **Testes sandbox:** py_compile OK. Suite de certidão/casamento/modelos_moldes/crc/sirc (53 arquivos): 509 passed, 9 failed — TODAS pré-existentes (mesmas falhas no INSTALAR/código sem o patch: RI cabecalho CNPJ, inteiro teor layout datas, problema_84 1ª via gratuita, credencial CRC eletrônica, ODT campos da casa). Prévia local 8366: quadro/ODT/teor «COMUNHÃO PARCIAL DE BENS»; acervo 1257 intacto.
- **Serviço:** sandbox :8899 recarregado pelo ciclo normal. Produção: cópia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar` → RESULTADO OK; PID 3052 → 18200; /saude 3.6.288.
- **Validação em produção (só leitura, banco `?mode=ro`, sem POST de emissão):** quadro.regime = «COMUNHÃO PARCIAL DE BENS»; ODT `@regimebens` idem, sem «COMUNHAO_PARCIAL»; teor montado idem. Sem selar; sem gravar teor/testemunhas/hc.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado.**
- **Backup:** Program Files `*.bak-regime-20261008-105541` (2 arquivos); sandbox `*.bak-regime-*`; CartorioGestao/tmp/hotfix_regime_certidao_20261008/{pf_before,sbx_before,instalar_before}.
- **nota_dev:** HOTFIX_OFICIAL: certidão de casamento imprime regime por extenso (reusa regime_por_extenso do termo).
- **Sem selar. Sem alteração de schema/banco.**
- **Como verificar:** ficha do 8366 → emitir/prévia da certidão de casamento: campo «REGIME DE BENS DO CASAMENTO» = «COMUNHÃO PARCIAL DE BENS».

### HOTFIX-2026-10-08-05 - Folhas frente/verso automaticas no cabecalho de cada pagina (48, 48v, 49, 49v...) - Notas, RI ficha, Livro 3

- **Data/hora:** 2026-10-08 10:50 (America/Sao_Paulo).
- **Quem:** agente (Grok Bot), pedido da escrevente neste chat (08/10/2026 ~10:30): "Faca com que as folhas se modifiquem automaticamente - ex.: 48, 48 verso, 49, 49 verso - sem precisar modificar manualmente. EM TODAS AS ATRIBUICOES."
- **Versao em producao:** 3.6.288 (antes e depois; hotfix sem bump). /saude 10:50:09 e 10:51:03 = 3.6.288 ok.
- **Causa:** o cabecalho por pagina (termo/traslado das Notas, ficha RI, ficha Livro 3) usava um campo-formula `INT((PAGE-1)/2)+N` que o LibreOffice NAO recalcula ao converter: todas as paginas saiam com o mesmo rotulo ("FOLHA 48" repetido; ata 780 = 16 paginas todas "48"). A sobreposicao do PDF (`corrigir_rotulos_folha_livro_pdf`) so procurava a ancora "FICHA".
- **Mudancas:**
  - `ri_odt.py`: novos `PAGINAS_ROTULADAS=160`, `rotulo_face_da_pagina(folha_inicial, pagina)` e `_cadeia_de_paginas_rotuladas`: com cabecalho que tem #FOLHA_PAGINA# ou #FICHA#, o `styles.xml` ganha uma cadeia de estilos de pagina com o rotulo ESTATICO de cada face (Standard/Primeira = 48, Folha-002 = 48v, Folha-003 = 49 ... Folha-160; depois "Folha-resto" com a formula antiga). Funciona no LibreOffice sem recalculo. Documento sem marca de folha sai byte-identico ao anterior.
  - `impressao_pdf.py`: `corrigir_rotulos_folha_livro_pdf` procura "FICHA" e tambem "FOLHA" e nao toca na pagina cujo rotulo impresso ja esta certo (nao cobre "48 A 55" da 1a pagina, nao troca fonte).
  - `ra_ficha_odt.py` (Livro 3): com folha numerica o cabecalho usa "FLS. #FOLHA_PAGINA#" e passa `folha_livro_inicio` (42, 42v, 43...). Folha nao numerica: comportamento antigo.
- **Regra de inicio (ja existente, mantida):** Notas = cada ato comeca em folha nova (frente), folhas inteiras; verso que sobra sai inutilizado (regra de 17/08/2026 + paginas medidas de 07/10). Nucleo (RCPN/RTD/RCPJ/Protesto) = `escrituracao.reservar`/`livro_nucleo` (folha_nova/paginas_pares por serie; rotulo "14"/"14v" em nu_lugares). Contador `folha_atual` avanca sozinho; folha manual continua possivel.
- **Paths:** ri_odt.py, impressao_pdf.py, ra_ficha_odt.py.
- **Hashes (sha256, 16; Program Files = SANDBOX/sistema = INSTALAR):** ri_odt.py 7ECA70360930FA44 (antes 631CC591F50166B2); impressao_pdf.py 26FAEA0242140194 (antes D16BD00608D31ADE); ra_ficha_odt.py E2AAEB1EB8901C17 (antes D19A75C151D5DF67).
- **Testes sandbox (dirigidos, com timeout, copia leve da arvore):** test_folha_livro_verso, test_traslado_carimbo_e_assinaturas, test_ri_carimbo_igual_em_todos, test_ra_livro3_completo, test_notas_paginas_medidas (inclui LibreOffice real): ORIGINAL 8 failed/65 passed, PATCH 8 failed/65 passed - mesmas 8 falhas pre-existentes; nenhuma regressao. Sandbox :8899 reiniciado 10:43 com o codigo novo. Exemplos (copia do banco do sandbox): Notas termo/traslado ato 4 -> FOLHA 1 | 1v (PDF); RI ficha mat. 1 -> FICHA N 1, 1v, 2...; Livro 3 reg. 2 -> FLS. 42, 42v, 43... (folha 48 -> PDF FLS. 48 | 48v).
- **Servico:** copia elevada + `installer\reiniciar_servidor.ps1` -> RESULTADO OK (10:50:12-10:50:36); /saude 3.6.288.
- **Validacao em producao (so leitura):** codigo de Program Files gera 48, 48v ... 55v para folha_livro_inicio=48; ata 780 inalterada (livro 1, fls. 48 a 55, termo 9, teor sha 5f834547, selos ATANOT000000MNLIR1DE5DYD6047 / ATANOT000000HJOK3CMTG0WMBU02).
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado.**
- **Backup:** CartorioGestao/tmp/hotfix_folhas_fv_20261008/{pf_before,bak_sandbox,bak_instalar}; Program Files `*.bak-folhasfv-20261008`. Script idempotente patch_folhas.py (marcador HOTFIX-FOLHAS-FV).
- **nota_dev:** HOTFIX_OFICIAL: folhas frente/verso automaticas no cabecalho de cada pagina (Notas termo/traslado, ficha RI, ficha Livro 3) - rotulo estatico por pagina, sem depender de recalculo do LibreOffice. (sem chamado Ajuda aberto - registrado aqui)
- **Sem selar. Sem alteracao de schema/banco. Nenhum ato renumerado.**
- **Pendencias:** (1) Livro 3: folha ainda digitada (ra_registros.folha vazia nos 17 registros) - atribuicao automatica pelo contador fica para o projeto; (2) Word nao segue a cadeia de estilos de pagina do ODT (no Word o rotulo volta a ser o campo) - usar PDF/LibreOffice; (3) termo RCPN (`rcpn_termo_odt`) nao tem cabecalho por pagina (1 folha por assento; rotulo vem de nu_lugares); (4) acima de 160 paginas num so documento o rotulo volta para a formula; (5) legado: 259 atos de Notas sem folha numerica (folha digitada) e 395/414 rc_atos sem livro_id - so contados, nao alterados.
- **Como verificar:** /notas/atos/780/termo-livro?formato=pdf -> paginas FOLHA 48, 48v, 49 ... 55v; ficha RI em PDF -> FICHA N 1, 1v, 2...

### HOTFIX-2026-10-08-04 - RCPN: texto do termo de casamento (documentos sem duplicata, regime por extenso, «nesta cidade de») + óbito «nesta cidade de»

- **Data/hora:** 2026-10-08 ~10:38 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot), aprovação da oficial neste chat em 08/10/2026 ~10:31 («PODE CORRIGIR»). Caso: casamento 8366 (B-4, termo 1013, Pessoa Exemplo × Pessoa Exemplo), prévia antes de «Escrever o termo no assento».
- **Versão em produção:** 3.6.288 (antes e depois; hotfix sem bump). /saude = VERSAO.txt = INSTALAR = sandbox :8899 = 3.6.288.
- **Causa:**
  - `relacao_de_documentos` listava cada linha de `hc_documentos`, que guarda o mesmo documento uma vez por nubente (`de_quem` NUBENTE1/NUBENTE2) → cada documento saía duas vezes.
  - O regime vem gravado como CÓDIGO de `hc_schema.REGIMES` (tela de lavrar/habilitação) e saía cru: «sob o regime de COMUNHAO_PARCIAL».
  - Corpo padrão do código (sem ajuste da casa em `mo_modelos`) dizia «nesta {cidade_do_ato}» → «nesta Cidade Exemplo» (casamento e óbito). 445 teores gravados usam «nesta cidade de Cidade Exemplo».
- **Mudanças (só `rc_modelos_do_livro.py`):**
  - `relacao_de_documentos`: o mesmo texto entra uma vez só (apresentados e dispensados).
  - Novo `regime_por_extenso`: código conhecido → rótulo de `hc_schema.REGIMES` com inicial minúscula («comunhão parcial de bens»); texto livre do acervo passa como veio. Usado em `valores_do_casamento`.
  - `TERMO_CASAMENTO` e `TERMO_OBITO`: «nesta {cidade_do_ato}» → «nesta cidade de {cidade_do_ato}». Feito no padrão do código (mesmo arquivo, sem gravar override em `mo_modelos`), para não congelar o corpo nem divergir do sandbox; a casa continua podendo ajustar em Configuração → Modelos dos documentos.
- **Paths:** rc_modelos_do_livro.py
- **Hashes (prod = SANDBOX/sistema = INSTALAR):** a1924ca6ab51 (antes 1f728afa6432).
- **Testes sandbox:** py_compile OK. 38 arquivos (rc_assento, pessoas_do_assento, habilitacao, rc_requisitos_legais, modelos_da_casa, modelos_elementos, modelos_motor_2c, modelos_editor_*, modelos_motor*, rc_termo*, rc_modelos_do_livro, rcpn_casamento/obito/nascimento_ensaio, rc_certidao_molde_casamento/obito, selo_do_casamento, proclamas*, etc.): 622 passed, 1 failed pré-existente (test_habilitacao::test_os_proximos_passos_saem_do_estado — efeito do HOTFIX-2026-10-07-04). Prévia no sandbox: casamento 31 e óbito 29 com «nesta cidade de Cidade Exemplo».
- **Serviço:** sandbox :8899 recarregado pelo ciclo normal (start-sandbox-loop). Produção: cópia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar` → RESULTADO OK; PID 17680 → 12536; /saude 3.6.288.
- **Validação em produção (só leitura, banco `?mode=ro`, código de produção):** 8366 → «nesta cidade de Cidade Exemplo»; 4 documentos sem repetição; «sob o regime de comunhão parcial de bens»; «as testemunhas PESSOA EXEMPLO e PESSOA EXEMPLO» (gravadas antes, audit 28499); teor continua vazio; selo do ato 423 intacto.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado.**
- **Backup:** Program Files `rc_modelos_do_livro.py.bak-teor-20261008-103822`; sandbox `rc_modelos_do_livro.py.bak-teor-20261008-103245`; CartorioGestao/tmp/hotfix_teor_casamento_20261008/{pf_before,sbx_before,instalar_before}.
- **nota_dev:** HOTFIX_OFICIAL: termo de casamento sem documentos duplicados, regime por extenso e «nesta cidade de» (também no óbito).
- **Sem selar. Sem alteração de schema/banco.** Não mexe em Autorização (hc_documentos), testemunhas, teor, rc_atos nem selos; termo do 8366 continua NÃO escrito.
- **Pendências:** (1) a certidão de casamento (`rc_certidao.py`/`rc_certidao_quadro.py`) ainda imprime o regime como gravado — no 8366 sairia «COMUNHAO_PARCIAL»; (2) o termo só nomeia as testemunhas (art. 70, item 8, da Lei 6.015/1973 pede profissão, residência e nacionalidade); (3) tela «Editar» tem um só bloco de testemunha — não usar no 8366 (sobrescreveria o Pessoa Exemplo); (4) «Autorização» marcada como apresentada para nubentes maiores — oficial decidiu NÃO alterar.
- **Como verificar:** ficha do 8366 → Ver o termo (prévia): «nesta cidade de Cidade Exemplo», documentos uma vez cada, «comunhão parcial de bens», duas testemunhas.

### HOTFIX-2026-10-08-03 - Notas (procuracao/escritura): selo de arquivamento passa a ser o item 13.30 (era 16.39 do RI)

- **Data/hora:** 2026-10-08 ~10:21 (America/Sao_Paulo).
- **Quem:** agente (Grok Bot), pedido da escrevente escrevente neste chat (08/10/2026): "na aba de procuracoes, no local de gerar selos de arquivamento, esta o item 16.39; para procuracao e o 13.30 - verifique e arrume".
- **Versao em producao:** 3.6.288 (antes e depois; hotfix sem bump). /saude = VERSAO.txt Program Files = INSTALAR = 3.6.288.
- **Causa:** `notas_web._selar_arquivamento_das_notas` reaproveitava o arquivamento do RI: caminho `AS.CAMINHO_ARQUIVAMENTO_RI` (`/selo/imovel/atos-em-geral`) e item `AS.CODIGO_ARQUIVAMENTO_RI` (16.39), com a tabela de custas do RI (prefixo 02 -> `0220260101`). Tabela do TJMA no banco (cx_servicos): 13.30 (cod. 698, grupo 21 - Notas) e 16.39 (cod. 633, grupo 24 - RI), ambos "Arquivamento, por folha do documento". O acervo mede 712 usos do 13.30 em `/selo/notas/atos-em-geral` (atribuicoes.py).
- **Mudancas:**
  - `notas_web.py` (`_selar_arquivamento_das_notas`): item `13.30`, caminho `/selo/notas/atos-em-geral` (tabela de custas das Notas, prefixo 05 -> `0520260101`); envelope AtosEmGeral igual, com `ato.codigo` = 13.30; referencia `nt_atos:<id>:13.30:1`. Docstrings ajustadas. RI/Livro 3 (16.39) nao tocados.
  - `templates/notas_ato.html`: rotulos "Arquivamento do documento (13.30)" e "Selar arquivamento (13.30)". Alteracao pontual nas 3 copias (o template de producao ja diferia do SANDBOX/INSTALAR antes deste hotfix; diferencas preservadas).
- **Paths:** notas_web.py, templates/notas_ato.html.
- **Hashes (sha256, 16):** notas_web.py 2D20FA67D362AFA1 (Program Files = SANDBOX/sistema = INSTALAR); notas_ato.html Program Files F825374260DB60C5, SANDBOX/INSTALAR 5EFDD5532F89F1E2.
- **Testes:** py_compile OK; conferencia offline do envelope (ato_selado sem rede): `{"ato": {"codigo": "13.30", "codigoTabelaCusta": "0520260101"}, "quantidade": N}`. Bateria pytest nao rodada (venv de producao sem pytest).
- **Status:** ESPELHADO_SBX (SANDBOX/sistema e INSTALAR espelhados). Program Files copiado (copia elevada, `*.bak-20261008-arquiv1330`). **LIVE aplicado:** reinicio autorizado pela usuaria em 08/10/2026 ~10:29; `installer\reiniciar_servidor.ps1` (elevado) 10:29:48-10:30:00 RESULTADO: OK; PID 4704 -> 17680 (iniciado 10:29:56, depois da copia das 10:20); /saude 3.6.288 ok. Log: tmp/hotfix_arquiv_notas_1330_20261008/restart_live.log e reiniciar.log.
- **Backup:** CartorioGestao/tmp/hotfix_arquiv_notas_1330_20261008/ (pf_before/, sbx_before/, instalar_before/, patch.py, copy_live.log).
- **Dados:** nenhum. O item do arquivamento nao fica gravado no ato (nt_atos so tem selo_arquivamento/folhas_arquivamento, vazios no ato 788); nenhum selo pedido.
- **nota_dev:** HOTFIX_OFICIAL: Notas - selo de arquivamento 13.30 em /selo/notas/atos-em-geral (antes 16.39 do RI). (sem chamado Ajuda aberto - registrado aqui)
- **Sem selar.** Sem alteracao de schema/banco.
- **Como verificar (apos reinicio):** /notas/atos/788 -> quadro "Selar arquivamento (13.30)"; ao pedir, sd_selos.caminho = /selo/notas/atos-em-geral e referencia nt_atos:788:13.30:1.

### HOTFIX-2026-10-08-02 - Ficha RI: cabecalho do protocolo com data da prenotacao, abertura com titular de origem, carimbos sem selo cancelado/arquivamento duplicado

- **Id:** HOTFIX-2026-10-08-02. Os comentarios no codigo levam o marcador de preparo `HOTFIX-2026-10-07-04` (ri_web/ri_odt) e `HOTFIX-2026-10-07-04/selos` (ri_web); esse id ja tinha sido usado no registro por outro hotfix (Habilitacao), por isso o id oficial desta entrada e 10-08-02 - nao confundir com o HOTFIX-2026-10-07-04 de habilitacao.py.
- **Data/hora:** preparado 2026-10-07 ~18:05 (SANDBOX); publicado 2026-10-08 09:49 (America/Sao_Paulo).
- **Quem:** agente (Grok Bot / escrevente), pedido da escrevente - saneamento da matricula 4019 (Pessoa Exemplo, Lote 46, destacada do AV-29/582).
- **Versao em producao:** 3.6.288 (antes e depois; hotfix sem bump). VERSAO.txt INSTALAR = Program Files = 3.6.288.
- **Causa / pedido:**
  1. O cabecalho que a ficha monta pelos campos saia "PROTOCOLO N 11546, DE 2026-09-23" (numero sem ponto + DATA DO ATO em ISO). O cabecalho deve trazer numero e data do PROTOCOLO (prenotacao): "PROTOCOLO N 11.546, DE 04 DE AGOSTO DE 2026".
  2. A abertura listava como PROPRIETARIO(S) todos com proprietario_ativo (INCRA + adquirente do R-01). Na abertura vao os titulares de ORIGEM (partes da abertura: ato_id NULL e proprietario=1); o adquirente entra pelo R-01.
  3. R-01/4019 imprimia dois "SELO DE REGISTRO" (1/2 e 2/2): o primeiro (REGAVD000000P8Q2QYDPOSBRXS37) esta CANCELADO no razao (sd_selos.cancelado_em 23/09/2026 16:40, cancelado no Portal do Selo TJMA e reemitido isento FXF2). A lista do razao nao filtrava cancelados.
  4. AV-02/4019 imprimia o selo de arquivamento 16.39 duas vezes ("SELO DE AVERBACAO 2/2" + "SELO DE ARQUIVAMENTO (30 fl.)"), porque o 16.39 mora no razao com tabela='ri_atos' e o mesmo ato_id.
- **Mudancas:**
  - ri_web.contexto_ficha: protocolo_cab (numero com ponto) e protocolo_data_cab (data da prenotacao por extenso: ri_atos.prenotacao ou Livro 1 pelo numero, ate 365 dias antes do ato; sem achar, comportamento antigo); proprietarios_abertura (ato_id NULL e proprietario=1; vazio -> lista antiga).
  - ri_odt.MODELO_FICHA_PADRAO: cabecalho usa protocolo_cab/protocolo_data_cab; abertura usa proprietarios_abertura.
  - ri_web (ri_ficha tela + contexto_ficha certidao/.odt): lista de selos do ato com "cancelado_em IS NULL" e sem o numero gravado em ri_atos.selo_arquivamento (ele ja sai no carimbo proprio).
- **Testes (dirigidos, sem bateria completa):** 17 arquivos (relato_67/71/79/86, ri_assinatura_da_abertura, ri_ficha_modelo_atual, ri_carimbo_do_selo, ri_selo_da_abertura, ri_quem_pratica_o_ato, ri_regra_acervo_4015, ri_carimbo_igual_em_todos, busca_da_lista_de_matriculas, protesto_cenprot_web, ra_livro3_completo, ra_parte, rcpj_rtd_selo_automatico, livro3_arquivamento_e_arquivo) em copia leve da arvore: ORIGINAL 28 failed/215 passed, PATCH 28 failed/215 passed - mesmas 28 falhas (pre-existentes, testes defasados do codigo atual); nenhuma regressao. As 10 falhas da execucao de 07/10 (busca 1, protesto_cenprot_web 1, ra_livro3 1, ra_parte 1, relato_67 3, relato_71 3) falham igual no codigo original.
- **Paths:** ri_web.py, ri_odt.py.
- **Hashes (sha256, 16):** ri_web.py DFDFBC8D24B8E50E; ri_odt.py 631CC591F50166B2 (SANDBOX/sistema = INSTALAR = Program Files).
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado** (copia elevada + installer/reiniciar_servidor.ps1 RESULTADO: OK; /saude 3.6.288 ok antes 09:49:01 e depois).
- **Backup:** CartorioGestao/tmp/hotfix_ficha_4019_20261008/ (pf_before/, *.instalar_antes, ri_web.py.sandbox_antes_selos); scripts C:\Users\<usuario>\san4019\patch_ficha_protocolo_abertura.py e patch_selos_ficha.py (+ bak_*).
- **nota_dev:** HOTFIX_OFICIAL: Ficha RI - cabecalho com n. e data da prenotacao (sem duplicar), abertura so com titular de origem, carimbo sem selo cancelado e sem arquivamento duplicado. (sem chamado Ajuda aberto para este pedido - registrado aqui)
- **Sem selar.** Sem alteracao de schema. Dados da 4019/582 corrigidos a parte (saneamento de oficio, scripts apply_4019.py 07/10 e apply_582_4019.py 08/10; backups em ProgramData\CartorioGestao\backups_saneamento\).
- **Como verificar:** /registro-imoveis/5381/ficha.odt?formato=pdf -> R-01 "PROTOCOLO N 11.546, DE 04 DE AGOSTO DE 2026" uma vez; abertura PROPRIETARIO(S) so INCRA; R-01 um so SELO DE REGISTRO (FXF2); AV-02 SELO DE AVERBACAO + SELO DE ARQUIVAMENTO uma vez cada.

### HOTFIX-2026-10-08-01 - RCPN: selo em CARIMBO (QR) no termo/Folha + Folha ODT editavel + carimbo na certidao de habilitacao

- **Data/hora:** 2026-10-08 ~09:42 (America/Fortaleza)
- **Quem:** agente (Grok Bot), aprovacao da oficial neste chat em 08/10/2026 (~09:17: «Pode testar no 8899 e aplicar o hotfix do carimbo na producao»; ~09:25: «... e aplicar o carimbo da certidao de habilitacao na producao»). Pedido da escrevente: casamento 8366 (B-4, termo 1013) - «o selo tem que ser em carimbo como todo resto do sistema».
- **Versao em producao:** 3.6.288 (antes e depois; hotfix sem bump). /saude = VERSAO.txt = INSTALAR = sandbox :8899 = 3.6.288.
- **Causa:**
  - `atribuicoes_web._contexto_folha_do_assento` emendava `"\nSelo: <numero>."` no texto corrido do termo (Folha PDF/ODT de TODAS as especies do RCPN). `rcpn_termo_odt` e a Folha HTML nao tinham selo nenhum.
  - Folha ODT = `impressao_pdf.odt_de_pdf_visual`: paginas do PDF do Chrome viradas PNG - nada editavel.
  - `habilitacao_web.rcpn_habilitacao_certidao`: a certidao nao imprimia o selo.
- **Mudancas:**
  - `atribuicoes_web.py`: novos `_etiqueta_do_registro_rcpn` (etiqueta inteira de `sd_selos.texto` pelo NUMERO vigente em `rc_atos.selo`, nao cancelado - evita carimbo duplo em re-selagem, ex. 8298) e `_sem_selo_corrido` (tira «Selo: X.» so na IMPRESSAO; teor congelado intacto). `rcpn_termo_odt`, Folha HTML (`rcpn_folha`) e `_contexto_folha_do_assento` passam a desenhar `carimbo_compacto_odf`/`carimbo_compacto_html` (SELO DIGITAL DO TJMA + numero + emolumentos + link + QR). `rcpn_folha_papel?formato=odt` passa a gerar ODT EDITAVEL via `gerar_odt` (cabecalho termo/livro/folha + termo + carimbo + notas). PDF segue o visual de 3 colunas (Chrome), agora com o carimbo.
  - `templates/rcpn_folha_impressa.html`: `face.carimbo` abaixo do termo.
  - `habilitacao_web.py`: import `carimbo_compacto_odf`; certidao de habilitacao com carimbo + QR (via `AS.etiqueta_do_ato`); sem selo sai como antes.
- **Paths:** atribuicoes_web.py, templates/rcpn_folha_impressa.html, habilitacao_web.py.
- **Hashes (prod = SANDBOX/sistema = INSTALAR):** atribuicoes_web.py b88da6e26228; rcpn_folha_impressa.html a9aa5962fede; habilitacao_web.py 198b81990c33 (antes: 2b0ce77af732 / e6b5751553d0 / 0b41983fa254).
- **Testes sandbox:** py_compile OK. 20 arquivos (folha/termo/rcpn/carimbo/certidao/habilitacao/atribuicoes): 357 passed, 7 failed - TODAS pre-existentes/sem relacao: 5 em test_ri_carimbo_igual_em_todos.py (falham identicas no INSTALAR sem o patch; teste so importa ri_odt), test_habilitacao::test_os_proximos_passos_saem_do_estado («Aguardar o prazo» - efeito do HOTFIX-2026-10-07-04 em habilitacao.py), test_atribuicoes_web::test_o_rcpj_e_o_rtd_tem_cada_um_a_sua_lista (tela RCPJ, nao tocada). E2E sandbox (casamento 34, nascimento 33, HC 1): Folha HTML com carimbo+QR; Folha ODT e termo.odt com texto editavel + 1 carimbo + QR; PDF com carimbo; sem «Selo: X.» corrido; HC sem selo (copia do banco) sai sem carimbo.
- **Servico:** sandbox :8899 recarregado pelo ciclo normal (start-sandbox-loop: processo do app encerrado -> loop sobe de novo, 3.6.288). Producao: copia elevada + `installer\reiniciar_servidor.ps1 -Acao Reiniciar` -> RESULTADO OK; PID 3884 -> 19876; /saude 3.6.288.
- **Validacao em producao (so leitura):** codigo de producao + COPIA do banco (fonte `?mode=ro`, copia apagada ao fim; nenhuma auditoria/gravacao em producao). 8366: Folha HTML 1 carimbo+QR; Folha ODT/termo.odt editaveis com carimbo HABCAS0000008YNW0AD7VD386O11 (14.1.1, Total R$ 244,66) + QR; Folha PDF OK. 8298: 1 carimbo (REGNAS...WSZ7 vigente), «Selo:» legado tirado na impressao. HC 1 certidao 1/2026: carimbo HABCAS + QR, conferencia mantida.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado.**
- **Backup:** Program Files `*.bak-carimbo-20261008-094236` (3 arquivos); CartorioGestao/tmp/hotfix_carimbo_rcpn_20261008/{pf_before,sbx_before,instalar_before}; sandbox `*.bak-carimbo-20261008-091930`.
- **nota_dev:** HOTFIX_OFICIAL: RCPN selo em carimbo com QR (termo/Folha HTML/PDF/ODT), Folha ODT editavel, carimbo na certidao de habilitacao.
- **Sem selar. Sem alteracao de schema/banco.** Nenhum teor/rc_atos/selo alterado; termo do 8366 continua NAO escrito.
- **Pendencias:** (1) antes de «Escrever o termo» do 8366, revisar o texto do modelo de casamento (documentos duplicados por nubente, regime «COMUNHAO_PARCIAL» cru, «nesta Cidade Exemplo», 1 testemunha so). (2) Link do carimbo levemente mais largo que a coluna do termo no PDF (cosmetico). (3) Folha ODT editavel nao reproduz as 3 colunas/pauta (o PDF reproduz).
- **Como verificar:** ficha RCPN -> Folha (HTML)/Folha PDF/Folha ODT e Ver o termo -> Baixar .odt: carimbo SELO DIGITAL DO TJMA com QR abaixo do termo, texto editavel no ODT; ficha da habilitacao -> certidao ODT com carimbo.

### HOTFIX-2026-10-07-05 - Habilitação: dadosSelo.livro/folha/termo do proclamas (Livro D)

- **Data/hora:** 2026-10-07 ~14:28 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot), autorização teste cart (mesmo tema HC1 / habilitar).
- **Versão em produção:** 3.6.288 (antes e depois; hotfix sem bump).
- **Causa:** ao clicar Habilitar na HC1, o Tribunal recusou o selo: `dadosSelo.livro`, `folha` e `termo` obrigatórios (`HC_HABILITACAO_NAO_EXPEDIDA_SELO_FALHOU`). O assento de proclamas 8365 já tinha D-3 / 127 / 1359 (`proclamas_assento_id`), mas `_selar_a_habilitacao` em `habilitacao_web.py` montava `envelope_da_habilitacao` **sem** passar L/F/T (enquanto `atribuicoes_web` já passava ao selar PROCLAMAS).
- **Mudança:** em `_selar_a_habilitacao`, ler L/F/T do assento ligado (`livro_volume` / `numero` / `dados_json.folha`, com fallback `rc_matricula.partes`) e enviar no envelope; se faltar vínculo/LFT, recusar no balcão com mensagem clara.
- **Paths:** habilitacao_web.py
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files).
- **Backup código:** C:\ProgramData\CartorioGestao\tmp\hotfix_selo_lft_hab_20261007-142827\
- **Backup sqlite:** cartorio_gestao.antes-hotfix-selo-lft-hc1-20261007-142827.sqlite3
- **nota_dev:** HOTFIX_OFICIAL: selo da habilitação leva L/F/T do Livro D (proclamas_assento_id).
- **Sem selar automaticamente.** escrevente pode clicar Habilitar de novo.
- **Como verificar:** HC com `proclamas_assento_id` e L/F/T no assento → envelope traz livro/folha/termo; Habilitar não falha mais por esses campos.

### HOTFIX-2026-10-07-04 - Habilitação: expedir com edital publicado (sem esperar prazo)

- **Data/hora:** 2026-10-07 ~14:15 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot), autorização teste cart / Robô Casamento.
- **Versão em produção:** 3.6.288 (antes e depois; hotfix sem bump).
- **Causa / pedido:** após publicar o edital, o sistema bloqueava «Habilitar» enquanto o prazo de oposição (5 dias) estava em curso (`prazo_vencido`). A casa quer emitir a certidão de habilitação assim que o edital estiver publicado, mantendo o prazo só como informação na tela.
- **Mudanças:**
  - `habilitacao.py` `habilitar()`: removido o `raise` por prazo em curso; mantidos bloqueios de documentos, edital não publicado e oposição não decidida.
  - `habilitacao.py` `proximos_passos()`: com `EDITAL_PUBLICADO`, já sugere expedir; prazo de oposição permanece como linha informativa.
  - `templates/rcpn_habilitacao.html`: botão **Habilitar** sem `disabled` por `prazo_venceu`; texto do prazo só informativo.
  - `tests/test_habilitacao.py`: `test_nao_se_habilita_dentro_do_prazo` → `test_habilita_com_edital_publicado_mesmo_no_prazo`.
- **Paths:** habilitacao.py, templates/rcpn_habilitacao.html, tests/test_habilitacao.py.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files).
- **Backup:** C:\ProgramData\CartorioGestao\tmp\hotfix_habilitar_prazo_20261007-141427\
- **nota_dev:** HOTFIX_OFICIAL: Habilitação — pode expedir com edital publicado; prazo de oposição informativo.
- **Sem selar.** Sem alteração de schema/banco.
- **Como verificar:** HC com edital publicado e docs ok → botão Habilitar ativo; `HAB.habilitar` não levanta por prazo; certidão ODT após HABILITADO. e-Proclamas enviar continua ADMIN/MANAGER.

### HOTFIX-2026-10-07-03 - Tarefas: Cumprido conclui e sai das pendencias

- **Data/hora:** 2026-10-07 ~10:44 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot / escrevente cart3), continuidade do HOTFIX-2026-10-07-02 - ao marcar Cumprido a tarefa deve sumir das pendencias.
- **Versao em producao:** 3.6.287 (antes e depois; hotfix sem bump).
- **Causa / pedido:** Cumprido + anexo registrava andamento mas a tarefa continuava em «Em aberto» / ABERTAS.
- **Mudancas:**
  - app.task_detail action=note: apos gravar andamento tipo **CUMPRIDO** (com ou sem anexo), `update_task(status=CONCLUIDA)` + audit TASK_CONCLUIDA via=cumprido; mensagem «Cumprido: tarefa concluida e saiu das pendencias»; recado de expediente se houver (igual ao botao Concluir).
  - Guard `nota_ok` (nao conclui se notificar_para falhou sem gravar a nota).
  - templates/task_detail.html: dica de que Cumprido conclui e sai das pendencias.
- **Paths:** app.py, templates/task_detail.html.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files). **LIVE aplicado** (copia elevada + reinicio).
- **Backup:** CartorioGestao/tmp/hotfix_tarefas_cumprido_sair_20261007/
- **nota_dev:** HOTFIX_OFICIAL: Tarefas - Cumprido conclui e sai das pendencias.
- **Sem selar.** Sem alteracao de schema.
- **Como verificar:** /tarefas/<id> aberta -> Tipo Cumprido (+ anexo opcional) -> Registrar -> status CONCLUIDA; some do filtro Em aberto / ABERTAS.

### HOTFIX-2026-10-07-02 - Tarefas: andamento Cumprido + anexo do documento

- **Data/hora:** 2026-10-07 ~10:38 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot / escrevente cart3), pedido da escrevente - opcao Cumprido no historico e anexar o documento do cumprimento.
- **Versao em producao:** 3.6.287 (antes e depois; hotfix sem bump).
- **Causa / pedido:** na barra de historico/andamento das tarefas faltava o tipo **Cumprido** e a forma de anexar o documento que gerou o cumprimento (ja existiam Observacao, Emitida nota de exigencia, Aguardando o cliente, Cumprir exigencias, etc. desde HOTFIX-2026-10-01-01).
- **Mudancas:**
  - tarefa_processo.TIPOS_ANDAMENTO: novo codigo **CUMPRIDO** / rotulo **Cumprido**.
  - templates/task_detail.html: formulario do historico com enctype multipart; campo **Documento do cumprimento / anexo do andamento** (PDF/imagem/Office, multiplo).
  - app.task_detail action=note: grava upload em attachments(TASK) sob Evidencias/Tarefa-NNNNN, descricao «Documento do cumprimento» (ou «Anexo do andamento»), menciona o nome na nota, auditoria TASK_ANDAMENTO_ANEXO.
  - tests/test_tipos_andamento_tarefa.py: CUMPRIDO no vocabulario + test_cumprido_rotulo_e_normaliza.
- **Testes:** 4 passed (test_tipos_andamento_tarefa.py) no INSTALAR. /saude 3.6.287 apos reiniciar_servidor.ps1.
- **Paths:** tarefa_processo.py, app.py, templates/task_detail.html, tests/test_tipos_andamento_tarefa.py.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado** (copia elevada + reinicio).
- **Backup:** CartorioGestao/tmp/hotfix_tarefas_cumprido_20261007/
- **nota_dev:** HOTFIX_OFICIAL: Tarefas - andamento Cumprido + anexo do documento do cumprimento.
- **Sem selar.** Sem alteracao de schema/banco (usa attachments TASK ja existente).
- **Como verificar:** abrir /tarefas/<id> -> Historico e andamento -> Tipo «Cumprido» -> opcionalmente escolher arquivo -> Registrar; o nome aparece na nota e o arquivo em Evidencias.

### HOTFIX-2026-10-07-01 - Malote: barra de busca nos expedientes (n. do oficio / descricao)

- **Data/hora:** 2026-10-07 ~10:12 (America/Sao_Paulo)
- **Quem:** agente (Grok Bot / escrevente), pedido da escrevente — barra de busca por numero do oficio e descricao.
- **Versao em producao:** 3.6.287 (antes e depois; hotfix sem bump).
- **Causa / pedido:** a lista /expedientes (Malote) nao tinha filtro; achar oficio exigia varrer a tabela.
- **Mudancas:**
  - database.list_expedientes(..., busca=) — LIKE em external_reference, subject, notes, sender, internal_protocol, response_reference.
  - app.expedientes — le ?q= e passa busca ao template.
  - templates/expedientes.html — formulario GET Procurar, botao Limpar, coluna Referencia, contagem de resultados.
- **Testes (producao, so leitura):** list_expedientes(busca='18 2026') -> EXP-2026-000024; PORTARIA -> 2; xyznaoexiste -> 0; vazio -> 28. /saude ok 3.6.287 apos reiniciar_servidor.ps1.
- **Paths:** database.py, app.py, templates/expedientes.html.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema = INSTALAR = Program Files, hash conferido). **LIVE aplicado** (copia elevada + reinicio).
- **nota_dev:** HOTFIX_OFICIAL: Malote — busca de expediente por n. do oficio e descricao.
- **Sem selar.** Sem alteracao de banco.


### HOTFIX-2026-10-06-03 — SIRC: envio pela API não deixava rastro (registro voltava como devido)

- **Data/hora:** 2026-10-06 ~19:15 (America/Sao_Paulo)
- **Quem:** agente (Claude), ordem do oficial — «resolva todos problemas e atrasos da sirc» e «correcao agora. autorizo ler tudo».
- **Versão em produção:** 3.6.287 (antes e depois; hotfix sem bump).
- **Causa:** `atribuicoes_web.rcpn_sirc_arquivo_enviar` (e o do cancelamento) chamava `sirc_cliente.enviar`, mostrava a resposta e não gravava nada. `sirc_remessa.pendentes_de_remessa` devolve tudo sempre: o registro enviado voltava à tela no dia seguinte (podia ser mandado de novo) e `gestor_conferencia.regra_sirc` o cobrava como VENCIDO para sempre. Medido na produção (só leitura): `ge_envios` com **zero** linhas do SIRC.
- **Mudanças:** `sirc_remessa.py` — `referencia_do_envio` (a mesma chave da regra do gestor: `onde:assento_id:data do ato mais novo`), `ja_enviados`, `sem_os_ja_enviados`, `cancelamentos_sem_os_ja_enviados`; cada lote de `montar`/`montar_cancelamento` leva `referencias`. `atribuicoes_web.py` — tela, arquivo, `.mrc`, validar e enviar passam pela mesma lista filtrada (`_sirc_devendo`, `_sirc_cancelamentos`); envio aceito grava `ge_envios` (canal API, resposta do SIRC como protocolo, `origem='SISTEMA'`); recusado não grava; falha ao anotar avisa e não desfaz o envio.
- **Testes:** 6 novos (`tests/test_sirc_remessa.py` 4, `tests/test_sirc_remessa_tela.py` 2). No INSTALAR: SIRC + CSRF + gestor **133 ok**. Varredores no SANDBOX: nenhum achado destes arquivos (vermelhos são rascunhos `_tmp_*`/`tmp_*` e módulos de outras passadas). `tools/conferir_antes_de_atualizar.py`: PODE ATUALIZAR.
- **Paths:** `sirc_remessa.py`, `atribuicoes_web.py`, `tests/test_sirc_remessa.py`, `tests/test_sirc_remessa_tela.py` (SANDBOX e INSTALAR iguais, conferido por `cmp`; antes da cópia, as diferenças SANDBOX×INSTALAR nesses arquivos eram só estas).
- **Achados da mesma passada (produção, só leitura):** 14 pendentes (12 nascimentos 19566–19577 de 09 a 30/09, óbitos 1981 e 1982 de 24/09), nenhum retido. **Validação na Central:** «Usuário/senha inválido» — a credencial SIRC cadastrada (usuário = CPF do oficial) não é aceita pelo web service; envio pela API impossível até o oficial cadastrar a senha certa. Gerados para upload manual no SIRC-Web: `CartorioGestao/SIRC_ENVIO_06-10/sirc-nascimento-001.mrc` (12) e `sirc-obito-002.mrc` (2), com os `.xml` para conferência. Cancelamentos: 5 na lista, todos retidos ou de matrícula viva (8298, 8315) — não enviar sem conferir no SIRC-Web.
- **CONFERIDO NO SIRC-WEB (~19:20, login do oficial com certificado, só consulta):** 14 arquivos transmitidos desde 11/09 pela serventia (o último hoje 18h44, nascimento e óbito) — a casa vinha mandando à mão. «Pendências Atualizadas»: falta só o intervalo **19574–19575** de nascimento; óbito sem falta. «Movimentos com Erro»: 19572–19575 recusados em 22/09 e 30/09 com **«Dados Obrigatórios não informados: local»** (19572/19573 entraram depois). Por isso os `.mrc` gerados foram marcados NÃO ENVIAR (`CartorioGestao/SIRC_ENVIO_06-10_NAO_ENVIAR/`): dariam duplicidade e nova recusa.
- **Segunda parte do mesmo hotfix — o LOCAL do nascimento:** o montador nunca escrevia `<local>` (o XSD o declara `minOccurs=0`; a Central o exige). `sirc_remessa.py`: `LOCAL_NASCIMENTO_SIRC` (IBGE 1/2 -> UNIDADE_SAUDE, 3/5 -> FORA_UNIDADE_SAUDE), `<local>` depois de `horaNascimento`, e `o_que_falta` RETÉM nascimento sem local ou «ignorado» (9), dizendo onde informar. `atribuicoes_web.py` + `templates/atrib_rcpn_editar.html`: «Onde nasceu» na edição da ficha (grava por `RC.anotar_para_o_ibge`; mudar só o local também grava). Medido na produção: 19572–19575 (assentos 8283, 8290, 8291, 8298) têm `ibge_local_nascimento` vazio; os outros 8 têm 1 (hospital). Testes: +3 (`test_sirc_remessa.py` 2, `test_rcpn_editar_ficha.py` 1) e ajudantes de teste passam a gravar o local; todos os testes que tocam o SIRC: SANDBOX 258 ok, INSTALAR 213 ok; conferidor: PODE ATUALIZAR.
- **Falta, depois de aplicar (balcão/oficial):** (1) nos assentos 19574 e 19575 (e 19572/19573, para o sistema ficar igual ao SIRC), «Editar informações» -> «Onde nasceu: hospital», com motivo; (2) reenviar 19574 e 19575 ao SIRC (o `.mrc` sai da tela do SIRC — mas a lista ainda traz os 10 já aceitos, porque `ge_envios` está vazia: registrá-los em «Envios às Centrais» com o código do arquivo do SIRC antes de baixar o lote, ou digitar os dois direto no SIRC-Web); (3) a senha do SIRC para a API: «Usuário/senha inválido».
- **Status:** ESPELHADO_SBX. **LIVE pendente:** `SERVIDOR/ATUALIZAR_SISTEMA.cmd` como Administrador (só `atribuicoes_web.py`, `sirc_remessa.py` e `templates/atrib_rcpn_editar.html` diferem da produção 3.6.287).
- **nota_dev:** HOTFIX_OFICIAL: SIRC — envio pela API anotado em ge_envios; local do nascimento no arquivo e na edição da ficha.
- **APLICADO pelo oficial (~22h, conferido por hash: os 3 arquivos iguais à produção).**
- **Acréscimo ~23h20 (ESPELHADO_SBX, LIVE pendente):** `sirc_remessa.quantas_pendentes` — o painel das comunicações (`rc_obrigacoes._quantas`) contava o SIRC sem descontar o já enviado. +1 teste; INSTALAR 172 ok (SIRC, tela, obrigações, IBGE); conferidor PODE ATUALIZAR. Só `sirc_remessa.py` difere da produção.
- **Conferência no SIRC-Web, termo a termo (consulta de Registro de Nascimento 19560–19580 e de Óbito 1975–1990):** no SIRC 19566/19567 (arquivo 0415c54b…, 11/09 12h14), 19568–19571 e 19576 (49da371c…, 22/09 16h07), 19577 (1a25b305…, 30/09 16h48), 19572/19573 (69719153…, 06/10 18h44), óbito 1981 (369202bd…, 30/09) e 1982 (139072e4…, 06/10). **Faltam só 19574 e 19575.** O 19565 do SIRC é PESSOA EXEMPLO (Livro A-24, fl. 179, do E-Ofício, ausente do banco novo); o 19565 cancelado aqui (assento 1231, Pessoa Exemplo) é do Livro A-1 e nunca foi ao SIRC. **Os 5 cancelamentos da lista (1231, 8277, 8299, 8300, 8311) não se comunicam:** nenhum chegou ao SIRC, e 8300/8311 têm a matrícula de assento vivo. **Declaração de inexistência:** nenhuma devida — «Pendências Atualizadas» mostra 0 competências sem informação em nascimento, casamento, óbito e natimorto.
- **Credencial da API — achado no manual (seção 11.9.1 e pág. 105 do PDF):** a API usa o mesmo usuário/senha do portal (GERID desde a v2.4); **as funções de validação exigem o usuário de TESTE (usuário 123456, senha 1234, com o CNS da casa)**. O «Usuário/senha inválido» desta tarde foi a validação feita com a senha real — a senha do oficial pode estar certa para o envio. O botão «Validar» do sistema manda a senha real e por isso sempre recusará: a corrigir em `sirc_cliente.validar*`.
- **BLOQUEADO pela trava de segurança da sessão (não contornado):** gravar no banco da produção (`ibge_local_nascimento`=1 nos assentos 8283/8290/8291/8298; `ge_envios` dos 12 já aceitos e dos 5 cancelamentos DISPENSADOS — script pronto e não executado: scratchpad `sirc_acertar_producao.py`) e o caminho do envio ao SIRC. Ficam com o oficial pelas telas, ou com permissão.

### CGU 3.6.287 — 2026-10-06 (PREPARADO; aplicar pelo ATUALIZAR_SISTEMA ou /atualizacoes)

- **Ordem do oficial:** «vamos atualizar o sistema» (06/10/2026, fim da tarde).
- **O que leva (sobre a 3.6.286, 41 arquivos):**
  - **O agente gestor dentro do sistema** (até aqui só em `FERRAMENTAS/GESTOR`): `gestor_*.py`, telas «Envios às Centrais», «Leitura dos textos (IA)», «Caixas para o visto» e **«Relatório de erros»** (só ADMIN, com CSV), e o quadro «Erros abertos de quem praticou» no painel geral (só ADMIN).
  - **Revisão antes da lavratura (Opus 5.5)** no RI e nas Notas (`revisao_previa*.py`, `_revisao_previa.html`, `static/revisao_previa.js`; ganchos em `ri_web.py` e `notas_web.py`). GRAVE só lavra com justificativa escrita; IA fora do ar não trava. **Sem máscara** por decisão do oficial (`settings.revisao_mascara='1'` volta a mascarar).
  - **Avisos vermelhos:** caixa aberto depois das 14h / caixa de ontem aberto (`caixa_aviso*.py`) e ficha sem digitalização nova 7 dias depois do ato (`ri_digi_prazo*.py`).
  - **Tarefas do gestor didáticas** (`gestor_didatica.py`): por que existe, como resolver, e cada ato com «Onde abrir»; a tela da tarefa ganha o quadro «O que fazer» com os endereços como link.
  - **HOTFIX evidência** (ordem: «tire a regra de exigir evidencia para todas as tarefas e facilite a edicao»): a caixa «Exigir evidência» vem desmarcada (tarefa e obrigação recorrente), o padrão do banco para tarefa nova e para as recomendações da inspeção passa a 0, e a tela da tarefa tem **«Não exigir evidência»** / **«Passar a exigir evidência»** num clique (motivo opcional, auditoria `TASK_EVIDENCIA_ALTERADA`). **Na produção já em 06/10:** as 113 tarefas abertas que exigiam (78 inspeção, 25 manuais, 10 expedientes) passaram a 0 — lista em `docs/tecnico/hotfix_evidencia_20261006_tarefas_alteradas.json`, auditoria `TASK_EVIDENCIA_DISPENSADA_EM_LOTE`.
  - **Agente do sistema escondido** (ordem: «apenas não aparecer mais»): `agente_web.AGENTE_VISIVEL = False` — some o menu, o «configurar» e a gaveta; nada apagado.
  - **Da outra passada (SANDBOX-2026-10-06-03):** `ri_cnib.py`, `ri_minuta.py`, `tools/preencher_marcadores_das_minutas_cnib.py` — minutas CNIB com marcador cru (testada lá, produção não tocada).
- **Fora do pacote de propósito:** `dev_projetos.py` (o do SANDBOX difere só no fim de linha) e `ri_digitalizacao.py.before_hotfix_20261006` (sobra de hotfix, movida para `ARQUIVO_VERSOES_ANTIGAS/pre_3.6.287/_fora_do_pacote/`).
- **Backup do que foi substituído no INSTALAR:** `SERVIDOR/ARQUIVO_VERSOES_ANTIGAS/pre_3.6.287/` (refeito a partir do `.cgu` 3.6.286).
- **Validação:** suíte inteira `-n 4 --dist loadfile` na árvore da 3.6.287 (antes das duas últimas entregas): **7.619 ok, 128 falhas**, 15 pulados, 36 min. As 128 rodadas contra o código da 3.6.286 numa cópia isolada: **120 falham igual** (não são desta versão). Das 8 restantes: 3 passam sozinhas (credencial compartilhada entre processos paralelos), 5 eram desta versão e foram ajustadas no teste com o motivo escrito — o painel tem 4 tabelas com moldura (era 3), e a lista do RI passou a ignorar o aviso vermelho de digitalização ao medir a ordem. Depois das duas últimas entregas: 153 testes do gestor/tarefas/evidência ok; varredores sem nenhum achado de código desta versão (os vermelhos são os mesmos da 3.6.286: rascunhos e módulos de outras passadas). Validador do servidor (`validate_and_stage` + `inspect_staged`) rodado localmente: sem problema; aviso esperado «app.py alterado».
- **Pacote:** `VERSOES/CartorioGestao_3.6.287_20261006.cgu` (cópia na raiz de CartorioGestao), 10.435.004 bytes, SHA-256 `c3d0eebca82318655dda437ac7f555cb19b5253e2e03a89b09da8ce58809a908`, min-version 3.6.286; validador do servidor: ok, sem problemas.
- **Depois de aplicar:** `/saude` = 3.6.287. A conferência diária continua rodando de `FERRAMENTAS/GESTOR` (cópias iguais às do pacote).

### SANDBOX-2026-10-06-03 — CNIB: minutas com `{{ rotulo }}`/`{{ protocolo_frase }}` crus (produção NÃO tocada)

- **Data/hora:** 2026-10-06 ~12:40–13:10 (America/Sao_Paulo)
- **Quem:** agente (Claude), tarefa aberta pela conferência diária do gestor (regra MODELO_NAO_PREENCHIDO; ver o acréscimo 12:45 do HOTFIX-2026-10-06-01).
- **Versão em produção:** 3.6.286, **não alterada**. Nenhum arquivo de `C:\Program Files\CartorioGestao` nem linha do banco de produção foi escrito (banco lido só em `mode=ro`).
- **Causa:** `ri_cnib.teor_preparado` passava o modelo `AV-INDISPONIBILIDADE` só por `ri_modelos_atos.preencher`, que troca os `[COLCHETES]` e deixa o Jinja para `render_modelo` (`ri_web`) — ninguém o resolvia ali. Quem gravou as minutas foi `FERRAMENTAS/preparar_minutas_cnib.py` (04/10 «Codex», 06/10 «Claude»), chamando o `ri_cnib` instalado. **A rota de lavrar (`ri_lavrar_ato`) grava o teor como vem do formulário, sem motor de modelo:** lavrar qualquer das 11 poria o marcador no livro e na corrente de hash. Medido na produção: **0 atos** e **0 rascunhos** com `{{`; 11 minutas A_REVISAR e 5 DESCARTADAS com ele. A tela «CNIB — pendentes» também mostrava o teor cru. **Correção ao enunciado da tarefa:** o `ri_web.py` vigente TEM `protocolo_frase` (linhas 4607 e 4708, em `_contexto_modelo` e `ri_aplicar_modelo`) — o defeito não era a rota ter perdido o contexto, e sim `ri_cnib` nunca o ter usado.
- **Mudanças (SANDBOX/sistema):**
  - `ri_cnib.py`: `parte_fixa()` nova (rótulo e frase do protocolo pela régua da rota de lavrar — `piso_do_proximo` em ficha estruturada; em ficha de **ACERVO** o número não se inventa e fica `AV-[NUMERO DO ATO]/N`; prenotação ABERTA mais recente ou `[INFORMAR O PROTOCOLO].`); `teor_preparado(ordem, con, matricula_id, numero=)` troca os marcadores **no modelo, antes** de os dados da CNIB entrarem, e recusa marcador desconhecido; `pendentes()` passa a matrícula.
  - `ri_minuta.py`: `marcador_de_modelo()`; `criar` e `atualizar` recusam teor com `{{ }}`/`{% %}` (o `[colchete]` continua aceito).
  - `ri_web.py` (`ri_lavrar_ato`): recusa lavrar teor com marcador de modelo cru, antes de tomar número ou pedir selo. `ri_web.py` estava com data de 08:27 ao ser editado — sem passada concorrente.
  - `tests/test_cnib_minuta_sem_marcador.py` (9 testes, novos) — inclusive o caminho do script (`teor_preparado` -> `ri_minuta.criar`) e a rota recusando.
  - `tools/preencher_marcadores_das_minutas_cnib.py` (novo) — para as 11 da produção. **Só mede por padrão**; com `--confirmar` faz `VACUUM INTO` (recusa antes se não houver espaço), troca só os dois marcadores, grava `numero_pretendido` quando `--numero MINUTA=N` vem do livro, recusa número ocupado/escrito na ficha/repetido no lote, audita `RI_MINUTA_MARCADOR_PREENCHIDO` com o teor anterior. Medido contra a produção: **11 minutas, todas de ficha ACERVO, nenhuma com `numero_pretendido` e nenhuma matrícula com prenotação aberta** — sem `--numero`, o rótulo fica `AV-[NUMERO DO ATO]/N` e a frase `[INFORMAR O PROTOCOLO].`. Ensaiado numa cópia reduzida (só as tabelas que ele toca): 10 gravadas, a 31 recusada por repetir o número da 30 na mesma ficha, conferência pós-gravação limpa, segunda rodada idempotente.
- **Testes:** 9 novos ok; vizinhos (CNIB, minutas, lavrar, numeração, gestor, varredores) 262 ok. **Vermelhas que não são desta passada:** `test_debitos_do_balcao` (3 — falham igual no INSTALAR 3.6.286, rodado sem cache) e `test_portabilidade` (2 — rascunhos `_tmp_*`, `tmp_*` e módulos de outras passadas; nenhum arquivo desta lista).
- **Não feito, e declarado:** (1) `FERRAMENTAS/preparar_minutas_cnib.py` (gravado 12:24 por outra sessão) não foi tocado; quando o `ri_cnib` novo estiver instalado, a chamada deve passar a matrícula: `CNIB.teor_preparado(o, con, m["id"])`. (2) `ri_web._contexto_modelo` numera por `MAX(numero)+1` de `ri_atos`, e não pelo piso que a rota de lavrar usa — divergência anotada, não consertada.
- **DISCO C: CHEIO — medido durante esta passada:** 402 MB livres às 13:04, 24 MB às 13:05, ~105 MB às 13:07 (algo de fora grava e apaga). O banco tem 1,07 GB e `C:\ProgramData\CartorioGestao\backups` tem **33 GB**. Nenhuma cópia de segurança do banco cabe hoje, e o SQLite recusa gravar com disco cheio. Nada foi apagado: decisão do oficial.
- **Status:** SÓ SANDBOX — não espelhado no INSTALAR, não aplicado. Aplicar o script nas 11 minutas **espera ordem do oficial** (e espaço em disco para a cópia).
- **nota_dev:** CNIB — minuta preparada com marcador de modelo cru; preparação, minuta e lavratura passam a recusar/resolver.

### HOTFIX-2026-10-06-02 — Produtividade: botão inerte com cronômetro aberto de outro dia

- **Data/hora:** 2026-10-06 ~11:10 (America/Sao_Paulo)
- **Quem:** agente (Claude), relato do oficial — «deu um pequeno bug no botao de produtividade da gabriela, verifica pq ele ficou inerte».
- **Versão em produção:** 3.6.286 (antes e depois; hotfix sem bump).
- **Causa (reproduzida numa cópia isolada da 3.6.286, banco novo, porta 8931):** `cronometro_em_andamento` calculava o decorrido com `minutos_entre_horas(hora_inicio, agora)` — só relógio, sem data. Cronômetro aberto num dia e lido no seguinte com a hora atual antes da hora de início (ex.: iniciado 23:30, lido 11:00) -> `ValueError` «início depois do fim» -> **HTTP 500 em `/api/cronometro/status` e `/api/contexto`**. O painel abria sem o cronômetro, «Iniciar» respondia o mesmo erro (400) e não havia como parar: o usuário ficava preso. **Não conferido no banco da produção** (leitura bloqueada na sessão); o estado exato do registro da escrevente não foi visto.
- **Mudanças (`produtividade.py`):** decorrido com data+hora (`_minutos_desde_o_inicio`); `_enriquecer_registro` não derruba tela por registro gravado inconsistente (marca `horario_inconsistente`); `parar_cronometro` de outro dia fecha às 23:59 do dia em que começou, com observação «confira a duração» (não inventa as horas da noite).
- **Testes:** `tests/test_produtividade.py` 31 ok (3 novos). Conferido no navegador na cópia isolada: status 200, botão mostra o cronômetro de ontem, «Parar e salvar» ok, novo cronômetro pode iniciar.
- **Paths:** `produtividade.py`; `tests/test_produtividade.py`.
- **Status:** ESPELHADO_SBX (SANDBOX/sistema e INSTALAR iguais). **LIVE pendente:** aplicar com `SERVIDOR/ATUALIZAR_SISTEMA.cmd` (único arquivo diferente entre INSTALAR e Program Files, conferido por hash).
- **nota_dev:** HOTFIX_OFICIAL: produtividade — cronômetro de outro dia travava o botão (status/contexto 500).

### HOTFIX-2026-10-06-01 — Gestor: conferência diária ligada na produção (fora do Program Files)

- **Data/hora:** 2026-10-06 09:55 (America/Sao_Paulo)
- **Quem:** agente (Claude), por ordem do oficial — «pode ligar a conferencia diaria. nao crie tarefas para atos praticados antes de 10 de setembro de 2026».
- **Versão em produção antes e depois:** 3.6.282 (`/saude` conferido depois da rodada; servidor não foi parado nem tocado).
- **O que entrou:** pasta `FERRAMENTAS/GESTOR/` com `gestor_schema.py`, `gestor_conferencia.py`, `gestor_rotina.py`, `gestor_envios.py` (cópia do SANDBOX), `conferencia_diaria.py` e `CONFERENCIA_DIARIA.cmd`. Os módulos da casa que o gestor consulta (SIRC, CRC, FUNAI, CENSEC, DOI) vêm do **Program Files instalado**, que não foi alterado.
- **O que escreve no banco de produção:** tabelas novas `ge_envios`, `ge_achados`, `ge_execucoes`, `ge_responsaveis` (CREATE IF NOT EXISTS) e tarefas com `source_type='GESTOR'` em `tasks`/`task_history`. Não lavra, não sela, não cobra, não envia a Central.
- **Agendamento:** tarefa do Windows `CartorioGestao-Conferencia-Diaria`, todo dia 07:30, usuário `usuario` (sessão aberta), roda ao ligar se perdeu o horário.
- **Backup antes da primeira escrita:** `C:\ProgramData\CartorioGestao\backups\antes_gestor_conferencia_diaria_20261006_095217.sqlite3` (integrity_check ok, 271 tarefas).
- **Primeira rodada:** 48 achados, 15 tarefas (escrevente 4, escrevente 4, escrevente 3, escrevente 3, escrevente 1), 0 «não mediu». Log em `FERRAMENTAS/GESTOR/CONFERENCIA_DIARIA.log`; relatório em `FERRAMENTAS/GESTOR/relatorios/`.
- **Desfazer:** desativar a tarefa do Agendador; `UPDATE tasks SET status='CANCELADA' WHERE source_type='GESTOR'`; as tabelas `ge_*` podem ficar (nada as lê fora do gestor).
- **Para o Project:** o gestor ainda NÃO está no INSTALAR nem na 3.6.286. Quando entrar num pacote, a pasta `FERRAMENTAS/GESTOR` passa a importar do instalado e pode ser aposentada. 27 testes em `SANDBOX/sistema/tests/test_gestor.py`.
- **Status:** ESPELHADO_SBX (o código-fonte vive no SANDBOX; nada mudou em `C:\Program Files\CartorioGestao`).
- **Acréscimo 11:32 — camadas 2 e 3** (ordem «sigamos com as demais camadas»): regras novas copiadas para `FERRAMENTAS/GESTOR` — numeração do RCPN e do RI, corrente de hash do RI, ato do RI sem auditoria de lavratura, registro sem prenotação amarrada, selo fora do razão / razão sem ato, CPF/CNPJ inválido, caixa não conferido / diferença sem justificativa / caixa esquecido aberto, e o fechamento mensal selos × caixa. Rodada na produção (já na **3.6.286**): 109 achados, +7 tarefas, 0 «não mediu». 40 testes. **Também 06/10:** as 6 tarefas de carga da inspeção (#34, #36, #37, #38, #40, #41), que estavam sem responsável, passadas ao pessoal da atribuição por ordem do oficial, com linha `PASSAGEM` no histórico.
- **Acréscimo 12:45 — financeiro, resumo semanal e camada 4** (ordem «avance com o resto»): `gestor_financeiro.py` (relatório do mês e resumo da semana em `relatorios/`, só leitura, banco aberto em `mode=ro`); camada 4a por regra (texto do R/minuta/escritura contra o cadastro; campo de modelo não preenchido); camada 4b `gestor_leitura.py` — a IA lê o texto **mascarado** (`ajuda_privacidade.sanitizar_para_modelo`) pelo provedor **Claude** (chave já cadastrada; o DeepSeek devolveu resposta vazia em 2 de 3), teto de 25 leituras/dia, tabela nova `ge_leituras`. Achados da 4b são ATENÇÃO/CRÍTICO para quem qualifica; a IA não decide. **Achado de código, não consertado aqui:** 11 minutas CNIB (`ri_minutas` 20, 24, 27–35) com `{{ rotulo }}`/`{{ protocolo_frase }}` crus — tarefa separada aberta. 56 testes.
- **Acréscimo 13:05 — retificações** (ordem «verifica, retifica, resolve, continua»): (1) regra nova `MINUTA_EM_FICHA_ENCERRADA` — minuta A_REVISAR numa ficha encerrada; na produção acusou as minutas 14–17 (fichas provisórias 904020/904021, ENCERRADAS), +1 tarefa para a qualificação do RI. (2) Financeiro: o operador do caixa aberto só com o primeiro nome passa a contar com o nome do cadastro; seção nova «Atos do RI acima de R$ 1.000: de onde veio o dinheiro», casando pelo nome do depositante **inclusive cortado** no selo («PESSOA EXEMPLO»). (3) Os quatro módulos do gestor tinham **33 recortes de texto no SQL** (`substr`/`||`), e o teto de módulo novo em `test_portabilidade` é zero: trocados por `LIKE`/comparação de texto e recorte em Python — zero agora. **Correção de leitura minha:** os depósitos de agosto de Pessoa Exemplo e Pessoa Exemplo **têm** lançamento de uso (a descrição traz «… no protocolo 2026.08.146»); só o de Pessoa Exemplo (DP2026.08.3, R$ 6.499,31) está encerrado sem uso. 61 testes do gestor rodados numa cópia congelada da árvore (outra passada gravava no SANDBOX e o guarda da suíte anulava as rodadas). Vermelhas de `test_portabilidade` que **não** são desta passada: rascunhos `_inspect_mj*.py`, `_tmp_scan_*.py`, `_verify_mj.py` (recorte e PRAGMA) e `centrais_log.py` (PRAGMA), `ri_web.py` (data no SQL). Rodada na produção 13:02: 128 achados, 0 «não mediu».
- **Acréscimo 13:35 — continua.** (1) **Duas telas novas, só no SANDBOX** (vão no próximo pacote, quando o oficial mandar): Administrativo -> «Envios às Centrais» (`gestor_web.py`, `templates/gestor_envios.html`) — mostra o que a conferência cobra das Centrais e registra o envio com protocolo **pelas chaves do próprio achado**, sem ninguém digitar `rc_assentos:…`; e «Leitura dos textos (IA)» (`templates/gestor_leituras.html`) — os apontamentos da IA com o botão «conferi» (`gestor_leitura.marcar_revisado`, que não tinha tela). Ligadas no `app.py` e no menu (`base.html`). (2) **A rodada diária passou para dentro do pacote** — `gestor_rotina.rodada_diaria` (leitura -> conferência -> financeiro); `FERRAMENTAS/GESTOR/conferencia_diaria.py` agora só a chama. Rodada na produção 13:29 pelo caminho novo: igual (128 achados, código 0). (3) **Regra nova `DISCO`** (TI): espaço livre abaixo de 20 GB vira ATENÇÃO, abaixo de 5 GB CRÍTICO, listando as cópias soltas na pasta de dados; não apaga nada. **Por quê:** às 13h07 o disco C: chegou a **24 MB livres** e uma gravação minha falhou («no space left on device»). Apaguei a minha cópia da produção no rascunho (1 GB, `copia_producao.sqlite3`) e uma cópia da árvore; às 13h33 havia **34,5 GB** livres — cerca de 33 GB foram soltos por outro processo, **que não identifiquei**. O banco de produção conferido depois: WAL vazio, nada perdido. Na pasta de dados há ~1,4 GB em cópias soltas (`.bak_*`, `.backup-acervo-*`). (4) `gestor_schema.py` declarado entre os donos do `PRAGMA` em `test_portabilidade` (é módulo de esquema; o `table_info` é a migração). 69 testes do gestor; os varredores de CSRF, menu, tela em instalação nova, rota sem tela e função sem tela não acusam nada do gestor.
- **Acréscimo 13:50 — ordens do oficial** («deixa o usuario de teste… aviso grande, vermelho e insistente… tarefa critica para beatriz… de pessoa exemplo apenas avisa»): (1) usuário `teste` mantido e fora da cobrança (`TESTES_MANTIDOS_PELO_OFICIAL`); a tarefa #286 fechou sozinha na rodada das 13:49 (127 achados). (2) **Na produção, tarefas MANUAL para escrevente, criadas em nome do oficial (created_by=1):** #308 CRÍTICA, prazo 08/10 — regularizar os atos do RI de setembro sem pagamento achado (Pessoa Exemplo R$ 25.953,62; Pessoa Exemplo R$ 3.578,55; Pessoa Exemplo falta R$ 3.952,56; desmembramento de Pessoa Exemplo R$ 5.460,36 e sobra de R$ 1.590,72 no depósito de Pessoa Exemplo), começando por fechar o caixa aberto desde 14/09; #309 MÉDIA, prazo 13/10 — aviso do depósito de Pessoa Exemplo (DP2026.08.3, encerrado sem uso) e dos depósitos abertos sem uso. (3) **Só no SANDBOX (vai no próximo pacote):** `caixa_aviso.py` + `caixa_aviso_web.py` + `templates/_caixa_aviso.html`, incluído no `base.html` e ligado no `app.py` — depois do fim do expediente (configuração `caixa_fim_do_expediente`, padrão 17:00, porque o movimento medido de setembro termina entre 16h e 17h) o caixa de hoje aberto põe faixa vermelha e janela que volta a cada tela; caixa de dia anterior aberto **tranca as outras telas** (só a do caixa fica livre) para quem não é ADMIN; o ADMIN vê a lista dos caixas de outros dias abertos. Medido antes: 43 de 51 caixas desde 15/08 foram fechados só no dia seguinte. 6 testes em `tests/test_caixa_aviso.py`. **Acréscimo 13:58:** o oficial informou o horário — expediente até 14h, saída 14h15, aviso às 14h; padrão passou a `14:00`. **Pacote segurado por ordem dele.**
- **Acréscimo 16:30 — «agente completo que faça todo trabalho do oficial amanhã».** Na produção (FERRAMENTAS/GESTOR; módulos novos `gestor_caixa.py`, `gestor_expedientes.py`, `caixa_aviso.py`): (1) **caixa às 14h** — a tarefa agendada passou a rodar 07:30, **14:00 e 14:30**; caixa do dia aberto depois das 14h vira tarefa CRÍTICA **para a pessoa** (`setor PESSOA:<id>`), e o caixa esquecido também deixou de ir para a Gestão (comparação de nome em Python: o `upper()` do SQLite não trata o «ú» de Araújo). (2) **parecer dos caixas fechados** — o agente refaz a conta com `caixa_schema.resumo_caixa`: 42 dos 49 fecham (tarefa «falta o seu visto»), 7 com ponto escrito (troco de R$ 300 guardado antes de contar, lançamento sem forma de pagamento). **O agente não grava `conferido_por`** (é o id de quem conferiu); a tela do visto em lote está no SANDBOX. (3) **triagem do malote** — a IA lê expediente + PDFs (mascarados), e o agente abre a tarefa ligada ao expediente para o setor, com prazo, passos, rascunho de resposta e **pesquisa automática do CPF/CNPJ citado nos índices do RI**; circular de ciência vai ao despacho. 19 expedientes lidos, 8 tarefas (a duplicata #321 cancelada — o expediente 8 é cópia do 7). Os nomes voltam ao texto da tarefa (o mapa da máscara vive só na triagem). (4) **prenotação a vencer** — 5 dias úteis antes, tarefa da qualificação do RI. (5) **despacho do oficial** — tarefa `DESPACHO` diária para o ADMIN (a de ontem fecha). (6) **cobrança da equipe** — toda tarefa vencida da equipe (GESTOR, EXPEDIENTE, MANUAL, INSPEÇÃO) leva nota diária; prioridade só sobe nas do gestor. Achados urgentes do malote: DESPACHO-COGEx 182/2026 (reforma da sede) prazo 09/10; DECISÃO-COGEx 1635/2026 vencida desde 10/09 (pesquisa: nenhum imóvel com os CNPJs). 98 testes do gestor.
- **Acréscimo 18:30 — revisor antes da lavratura, trava da digitalização e revisão em lote.**
  (1) **Revisor antes da lavratura (Opus 5.5) — só SANDBOX, vai no pacote:** `revisao_previa.py`,
  `revisao_previa_web.py`, `templates/_revisao_previa.html`, `static/revisao_previa.js`; ligado em
  `ri_lavrar_ato` (ri_web.py) e na ação «lançar» das Notas (notas_web.py), e nas telas `ri_ficha`,
  `ri_preencher` e `notas_ato`. Botão «Revisar com IA»: lê o ato com a ficha inteira (RI) ou as
  partes (Notas), mascarado, modelo `claude-opus-5-5`, em segundo plano. Trava: sem revisão do texto
  que se lavra -> recusa; lendo -> recusa; GRAVE -> só com justificativa escrita (gravada em
  `rv_revisoes`); IA fora do ar ou leitura presa >6 min -> **não trava**. Sem chave da IA, ou
  `settings.revisao_previa='0'`, a etapa não existe (os testes de lavratura não a veem). Custo
  estimado US$ 4/mês (RI e Notas), preço Opus 5.5 US$ 4/20 por milhão.
  (2) **Trava da digitalização em 7 dias corridos — já na produção pelo gestor**
  (`ri_digi_prazo.py`, regra `DIGITALIZACAO_DA_FICHA` para o RI operacional e
  `DIGITALIZACAO_ATRASADA` para o administrador, ambas CRÍTICAS quando vencidas — aparecem na
  janela de avisos da casa). A data que vale é a do ARQUIVO da imagem: a «Importação pasta 7» de
  03/10 regravou `digi_em`, e nas fichas 3247 e 4004 a imagem é de 27/09, anterior ao ato. Na
  produção: 7 fichas vencidas (4017–4021, 3247, 4004), tarefas #327 (escrevente) e #328 (oficial).
  Aviso vermelho na tela (`ri_digi_prazo_web.py`, `_digi_aviso.html`) vai no pacote. Não impede
  lavrar.
  (3) **Revisão em lote dos atos passados por agente, sem API** — `tools/revisao_em_lote.py`
  (exportar mascarado em lotes de 25 com `INSTRUCAO.md`; `--sem-mascara` só por decisão do oficial;
  importar grava em `rv_revisoes` com origem AGENTE). Regra `REVISAO_DO_AGENTE` (gestor, já na
  produção) e «conferi» na tela das leituras (pacote). Primeiro lote: os 29 atos desde 10/09,
  revisados por dois agentes desta sessão. Acervo inteiro: 1.278 atos do RI (894 do E-Ofício), 264
  das Notas, 16 do Livro 3. (4) Achado de máscara: ela troca também município, nome de fazenda e
  número de matrícula por marcas — a revisão fica cega para confrontação e numeração (decisão do
  oficial). (5) Consertos: `gravar_achados` passou a atualizar a REGRA quando a chave volta com regra
  nova (o despacho dizia «0 caixas para o visto» com 42); `desmascarar` percorre listas.
- **Acréscimo 17:15 — revisão sem máscara, relatório de erros por pessoa, agente fora da tela.**
  (1) **«Liberar revisão sem máscara» (ordem do oficial, 06/10):** a revisão antes da lavratura,
  a revisão em lote e a leitura diária vão SEM máscara (`revisao_previa.mascarar_na_revisao`;
  `settings.revisao_mascara='1'` volta a mascarar sem versão nova). A triagem do malote continua
  mascarada. A leitura diária passou a ler também as AV do RI (com a ficha e os atos anteriores,
  `RV.dossie_ri_lavrado`) e o Livro 3, pula o ato já revisado antes da lavratura (mesmo hash),
  teto 40/dia. **Na produção** (FERRAMENTAS/GESTOR: `gestor_leitura`, `revisao_previa`,
  `gestor_expedientes`). Hoje leu 0 porque o teto do dia já estava gasto (60 leituras).
  (2) **Relatório de erros por quem praticou** (pedido 06/10): `gestor_erros.py` — os achados da
  conferência que são erro de quem praticou (20 regras: texto, selo, qualificação, caixa, prazo,
  comunicação), abertos e resolvidos, mais os atos lavrados contra apontamento GRAVE justificado.
  Autor pela coluna do ato e, vazia, pela AUDITORIA (24 dos 25 atos do RI desde 10/09 têm
  `lavrado_por` vazio); cada linha diz «como se soube»; sem fonte = «não identificado».
  Medido na produção: 122 erros, 113 abertos, 5 sem autor. **Na produção já:** o arquivo
  `relatorios/erros_AAAA-MM-DD.html` sai na conferência diária (gestor_rotina). **No pacote
  (segurado):** tela `/administrativo/gestor/erros` (só ADMIN, filtros, CSV), item no menu e
  quadro «Erros abertos de quem praticou» no painel geral (só ADMIN). 7 testes
  (`tests/test_gestor_erros.py`).
  (3) **Agente do sistema fora da tela** (ordem 06/10: «apenas não aparecer mais, desenvolvimento
  fica pro futuro»): `agente_web.AGENTE_VISIVEL = False` esconde o menu, o «Agente — configurar»,
  a gaveta e o `agente.js`. Nada apagado: rotas (ADMIN), tabelas `ag_*`, sessões e chave ficam.
  **Só no pacote** — até ele subir, a produção continua mostrando o agente ao ADMIN.
  Testes: 133 passando (gestor, agente, csrf, envios, erros). `test_portabilidade` acusa
  rascunhos de raiz de outras sessões (`tmp_*.py`, `_inspect_*.py`, `_patch_selo_robo_impl.py`,
  25/09 e 05/10) — nenhum módulo desta passada; declarados, não mexidos. (6) **Primeiro lote da revisão por agente, 19:10:** 29 atos desde 10/09 revisados por dois subagentes desta sessão e importados (`rv_revisoes`, origem AGENTE): 6 apontamentos GRAVES em 5 atos e 42 de atenção; tarefas #329 (RI) e #330 (Notas), escrevente. Conferidos no banco antes de importar: o R-4/1197 (hipoteca 1º grau, Banco De Lage Landen, R$ 97.650) NUNCA foi baixado e a AV-1 da 4017 o dá por cancelado; a matrícula 4019 tem `[INSERIR APÓS APRESENTAÇÃO DO DOCUMENTO]` no CCIR, CIB e CAR. A regra `MODELO_NAO_PREENCHIDO` passou a conhecer `[INSERIR|PREENCHER|COMPLETAR …]` e a olhar o teor das fichas abertas desde o corte (+8 achados). A trava de lavratura da outra sessão (`ri_minuta.marcador_de_modelo`) não recusa colchete, por decisão escrita nela — não alterada.

## CGU 3.6.286 — 2026-10-06 (APLICADO às 10:19 pelo ATUALIZAR_SISTEMA)

- **Pedido:** oficial, 06/10/2026 — «atualizar o cartorio gestao oficial com as mudancas feitas no sandbox» / «faca tudo para atualizar, empacote etc». Release (não hotfix), por ordem expressa dele.
- **Pacote:** `VERSOES/CartorioGestao_3.6.286_20261006.cgu` (cópia na raiz), **refeito às ~10h**: 1.082 arquivos, SHA-256 `00637ca2780e9a24d2a73ef14baa3b1693a0ea1f100a40dab8a6e08c3956948b`, min-version 3.6.282. O primeiro (`e858a436…89160`) foi **REJEITADO** pelo `/atualizacoes` às 09:55 (38 problemas: 33 rascunhos com BOM em `tools/` e 5 docs em UTF-16). Rascunhos movidos para `ARQUIVO_VERSOES_ANTIGAS/sync_sandbox_20261006-081751/limpeza_validador_servidor/`, docs convertidos para UTF-8 (INSTALAR e SANDBOX). O pacote novo passa no `validate_and_stage` + `inspect_staged` do próprio servidor (rodados localmente): `ok: True`.
- **`SERVIDOR/ATUALIZAR_SISTEMA.cmd`:** acrescentado `backups_patch` ao `/XD` do robocopy (o empacotador já excluía; o teste `test_as_pastas_excluidas_pelo_cmd_sao_as_do_empacotador` falhava desde a 3.6.282). Original em `ARQUIVO_VERSOES_ANTIGAS/sync_sandbox_20261006-081751/ATUALIZAR_SISTEMA.cmd.antes_backups_patch`.
- **Por que o ATUALIZAR_SISTEMA falhou antes:** a conferência da origem recusou — `app.py` e `VERSAO.txt` do INSTALAR com BOM, e 10 rascunhos em `tools/` (UTF-16/Latin-1) que não compilavam. Servidor não chegou a parar. Corrigido; conferência: 424/424 módulos, 276/276 telas, «PODE ATUALIZAR».
- **SANDBOX -> INSTALAR:** comparação a três vias com a produção como base. 42 copiados, 45 módulos novos (centrais fila/log/http/trava, A3, editor/motor de modelos, produtividade, selo robô, cpf_cnpj), 13 mexidos dos dois lados -> versão do sandbox (o INSTALAR era subconjunto, conferido trecho a trecho). Rascunhos `_*`/`tmp_*`/`backups_patch` não copiados. **`templates/ri_ficha.html` mantido do INSTALAR** (correção de 03/10: digitalização oficial antes das páginas do E-Ofício) e levado ao sandbox. Backup do que foi substituído: `SERVIDOR/ARQUIVO_VERSOES_ANTIGAS/sync_sandbox_20261006-081751/`.
- **Defeitos achados e corrigidos (INSTALAR e SANDBOX):**
  - `ri_web.py`: prenotação gravava o NOME em `ri_protocolos.criado_por` (FK para `users.id`) -> **HTTP 500 em toda prenotação**. Agora `usuario_id`.
  - `caixa_schema.marcar_usuarios_robo_por_nome`: lia `users.username` sem conferir a coluna -> derrubava `init_caixa_schema` (39 testes de custas/selo/caixa).
  - `modelos_editor(_web).py`: `/api/historico` e `/api/diff` sem parâmetro davam 400 (e `a=xyz` dava 500); agora padrão útil, 404 para id inexistente. +4 testes.
- **Validação:** suíte inteira `-n 4 --dist loadfile`: 7.451 ok, 154 falhas, 6 erros de coleta (ensaios que importam `SANDBOX/ambiente.py`). Das 154: 102 falham igual no código 3.6.282; 40 eram o defeito do caixa (corrigido); o resto é teste antigo (rótulo RCPJ/RTD, falsos de conexão, cronômetro dependente de relógio) ou efeito do B0 abaixo. Ensaio contra cópia da produção (rede bloqueada): 200 telas GET da 3.6.286, nenhuma 5xx, nenhuma pior que na 3.6.282.
- **PRÉ-REQUISITO ANTES DE APLICAR — B0 (dados da serventia):** a 3.6.286 tira do `serventia.py` os dados reais (titular, substituta, CNPJ, telefone, endereço, CEP, cidade, UF, e-mail; e muda nome, CNS do RI, brasão, host do selador). Sem eles em Configurações, os papéis saem com placeholder. Rodar ANTES: `SERVIDOR/MIGRACAO_SERVENTIA_ANTES_DA_3.6.286/1_MIGRAR_DADOS_DA_SERVENTIA.cmd` (simula, pergunta, grava só o que está em branco, backup automático). Testado em banco sintético; **não conferido na produção** (leitura do banco da produção bloqueada na sessão do agente).
- **Como aplicar (escolha do oficial, 06/10):** `SERVIDOR/ATUALIZAR_SISTEMA.cmd` como Administrador (copia o INSTALAR para `Program Files` e reinicia a 8765). Alternativa: `/atualizacoes` com o `.cgu` novo. Conferir `/saude` = 3.6.286.
- **Status:** APLICADO — `/saude` 3.6.286 desde 10:19 (`reinicio_do_servidor.log`). Migração B0 feita antes: gravação às 09:52 com backup `backups/cartorio_gestao.pre_b0_serventia_20261006_095227.sqlite3`; segunda rodada às 10:18 «nada a fazer».

## CGU 3.6.282 — 2026-10-01

- REURB: ri_web, ri_schema reurb_tipo, ri_protocolo/ficha templates

### HOTFIX-2026-10-01-01 - Tarefas: tipos de andamento (observação tipada) + demo #80

- **Data/hora:** 2026-10-01 ~10:07 (America/Sao_Paulo)
- **Quem:** agente executor (escrevente / cart3) — pedido: andamento tipado nas tarefas cadastradas; começar na tarefa #80
- **Motivo / problema:** No cadastro/edição/visão da tarefa o andamento era só texto livre (`NOTA`). Faltava escolher o **tipo** (emitida nota de exigência, aguardando cliente, cumprir exigências, em análise, documento pendente, etc.).
- **Mudanças:**
  - `tarefa_processo.py`: `TIPOS_ANDAMENTO` (9 tipos) + helpers; `notificar_para(..., tipo=)` grava código em `task_history.new_value` na NOTA
  - `database.py`: `add_task_note(..., tipo=)` persiste código em `new_value`
  - `app.py`: select no POST de andamento; andamento inicial opcional no cadastro; context processors
  - `templates/task_detail.html` + `tasks.html`: UI do tipo; timeline com rótulo do tipo
  - `tests/test_tipos_andamento_tarefa.py`
  - Demo DB: tarefa **#80** (Usucapião Extraordinária / EXP-2026-000002) com NOTA `EMITIDA_NOTA_EXIGENCIA`
- **Paths:** `tarefa_processo.py`, `database.py`, `app.py`, `templates/task_detail.html`, `templates/tasks.html`, `tests/test_tipos_andamento_tarefa.py`
- **Versao /saude oficial (8765):** **3.6.268** (antes 3.6.267; bump LIVE)
- **Sandbox / INSTALAR:** código espelhado; VERSION permanece **3.6.275** (já adiantada)
- **Status:** ESPELHADO_SBX + LIVE Program Files
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + LIVE)
- **Backup:** `C:\Users\<usuario>\cg_inspect_tarefas\bak_andamento_20261001-100505\` e `ProgramData\CartorioGestao\backups_patch\hotfix_tarefas_andamento_20261001-100505\`
- **Servico:** reinício :8765 OK; sandbox :8899 reiniciado
- **Como verificar:** `/saude` -> 3.6.268; abrir `/tarefas/80` -> Histórico com tipo «Emitida nota de exigência»; Nova tarefa / Registrar andamento -> select de tipo
- **nota_dev:** HOTFIX_OFICIAL: tipos de andamento em tarefas (demo #80)


## CGU 3.6.267 — 2026-09-30

### HOTFIX-2026-09-30-04 — Notas: data do teor no dia do selo (Ajuda #116)

- **Data/hora:** 2026-09-30 (America/Sao_Paulo)
- **Quem:** agente executor — fila Ajuda abertos espelhados prod/sandbox
- **Motivo / problema:** Escritura com teor montado dias antes saía na impressão/selo com data antiga no HTML gravado (`nt_atos.teor`), embora traslado já usasse «hoje» na exportação.
- **Paths:** `notas_teor.py` (`atualizar_teor_para_data_de_selo`, `valores_campos_data_lavratura`); `notas_web.py` (antes de `selar_o_ato_de_livro`); `notas_do_desenvolvimento.py` (#114–#116); `tests/test_relato_116_data_lavratura_selo.py`
- **Versao /saude oficial:** **3.6.267** (sem bump CGU — hotfix pontual .py)
- **Status:** ESPELHADO_SBX + LIVE Program Files
- **INSTALAR espelhado?** SIM
- **Como verificar:** pytest `tests/test_relato_116_data_lavratura_selo.py`; no balcão, ato com teor de outro dia -> «Pedir selo» -> data no teor = hoje; Ajuda #116 `NECESSARIO_TESTE`.
- **nota_dev:** HOTFIX_OFICIAL: data lavratura/selo alinha teor (#116); #114/#115 só validar login pós-267

**Titulo:** Avisos v2 faixas/modal — lote 3.6.261–3.6.267 (critico, ALTA badges, sem responsavel, Nao ha avisos)

- **Status:** APLICADO
- **Versao /saude prod (8765):** **3.6.267** (antes **3.6.260**)
- **Backup:** `backup_pre_atualizacao_3.6.260_para_3.6.267_20260930_151552.zip` (`ProgramData/CartorioGestao/backups/`)
- **Rollback CGU:** `ProgramData/CartorioGestao/updates/CartorioGestao_3.6.260_20260929.cgu`
- **Pacote:** `CartorioGestao_3.6.267_20260930.cgu` SHA-256 `69adde9ad8e5e86e7b628a56114bf6e4e01c0687baea89587282975907faf1a9`

### HOTFIX-2026-09-30-03 - CRC carga: CRMATESTANTEPRIMARIO maxLength 13

- **Data/hora:** 2026-09-30 ~15:40 (America/Sao_Paulo)
- **Quem:** agente executor (teste cart / Grok Bot) - pedido SERVIDOR: verificar erro XSD na ultima carga CRC e corrigir gerador
- **Motivo / problema:** Selecao do dia em `/rcpn/crc` (33 assentos; token `0c2a506c18454ce39db5d64e27ee1406`, 15:29) gerava XML que **falhava no XSD** `schemas/cargaRegistrosCompleto.xsd`.
- **Erro XSD exato:**
  - `Element 'CRMATESTANTEPRIMARIO': [facet 'maxLength'] The value has a length of '28'; this exceeds the allowed maximum length of '13'.`
  - idem length `25` no 2o obito
  - path: `/CARGAREGISTROS/MOVIMENTOOBITOTO/REGISTROOBITOINCLUSAO[n]/CRMATESTANTEPRIMARIO`
- **Carga:** regenerada em `Downloads\crc-carga-2026-09-30.xml` (27 inclusos / 6 retidos por municipio de nascimento ausente — retencao pre-existente, nao XSD). A carga em disco anterior `crc-carga-2026-09-22.xml` ja validava (sem CRM longo).
- **Causa:** `crc_carga.registro_de_obito` mandava `atestante_documento` cru (prosa livre, ex. `CRM-MA 0000 (IML Imperatriz)` / `CRM-MA 0000 (assistente)`). XSD limita CRM a 13; o nome do medico ja vai em `NOMEATESTANTEPRIMARIO`.
- **Paths:** `crc_carga.py` (`CRM_ATESTANTE_MAXLEN`, `_crm_atestante`); `tests/test_crc_carga.py` (2 regressoes)
- **Versao /saude oficial no momento:** **3.6.267** (antes=depois; hotfix minimo sem bump)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + LIVE Program Files)
- **Backup:** `ProgramData/CartorioGestao/backups_patch/hotfix_crc_crm_atestante_20260930-153838/crc_carga.py`
- **Servico:** reinicio :8765 OK apos publicar
- **Como verificar:** em `/rcpn/crc` baixar de novo a selecao; XML deve validar contra `schemas/cargaRegistrosCompleto.xsd`; tags `CRMATESTANTEPRIMARIO` = `CRM-MA 0000` / `CRM-MA 0000` (sem parenteses). Ou: `python -c` montar selecao + lxml XMLSchema.
- **nota_dev:** HOTFIX_OFICIAL: CRC CRMATESTANTEPRIMARIO maxLength 13 (prosa atestante_documento)

### HOTFIX-2026-09-30-01 - Person robots: grant CG map (escrevente/escrevente/escrevente/escrevente)

- **Data/hora:** 2026-09-30 ~13:55 (America/Sao_Paulo)
- **Quem:** agente executor (Grok Bot) — pedido: acesso DB/app dos person robots novos igual escrevente
- **Motivo / problema:** Robô escrevente não conseguia “incluir registro” no padrão do person bot escrevente. Investigação: users humanos já existiam (USER ativo); não havia mapa agent_id->users.id; perfil dos 4 novos só falava em *ler* código/banco (escrevente fala *alterar*); PROJETO listava só escrevente com serverId antigo `3916529`; tabela `robo` vazia.
- **O que bloqueava escrevente:** sem mapa canônico agent->usuário CG + instrução de perfil mais fraca que escrevente (não ACL Flask — role USER já cobre balcão/`/livro3/novo`). Não inventar user `Robô …` (`nome_humano`).
- **Mudanças:**
  - DB settings `grok_bot_personas` (JSON) + 5 linhas em `robo` (painel `/robos`)
  - Profiles Grok Bot dos 4 novos alinhados a poderes escrevente (alterar código/banco SERVIDOR; username/user_id)
  - `docs/tecnico/PROJETO_ROBOS_CARTORIO.md` §2b/2c (UUIDs + mapa)
- **Paths:** DB `ProgramData/CartorioGestao/cartorio_gestao.sqlite3`; `docs/tecnico/PROJETO_ROBOS_CARTORIO.md`; box profiles `sand-data/agents/<id>/profile.json`
- **Versao /saude oficial no momento:** **3.6.260** (sem bump — DB/doc/profile; sem .py)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + Program Files DOCUMENTACAO)
- **Backup:** `ProgramData/CartorioGestao/backups_patch/hotfix_person_robots_20260930-135500/`
- **Senhas:** não alteradas / não inventadas (person robots usam users humanos existentes)
- **Como verificar:** `SELECT value FROM settings WHERE key='grok_bot_personas'`; `SELECT id,nome,ato FROM robo`; `/robos` lista 5 person bots; insert de teste com `session["user_id"]=5` (gabriela) ou SQL audit `username_snapshot='gabriela'`
- **nota_dev:** HOTFIX_OFICIAL: person robots grok_bot_personas + PROJETO 2c (escrevente/escrevente/escrevente/escrevente)

### HOTFIX-2026-09-29-07 — RI certidão reprográfica: layout (A4, fichas cabem, capa/fecho)

- **Data/hora:** 2026-09-29 ~14:07 (America/Sao_Paulo)
- **Quem:** agente executor (escrevente / balcão — cert. reprográfica mat. 3750 «muito desajustada»)
- **Motivo / problema Ajuda:** Após HOTFIX-05 (título+fecho), o ODT reprográfico ainda saía torto: imagens com altura 27,9 cm em área útil ~27,1 cm (cortadas/sobrepostas); folha 21,5×27,9 desalinhada da proporção A4 das fichas; capa com título órfão; margem 0,4 cm; fecho com sha256 técnico no papel.
- **Paths:** `ri_digitalizacao.py` (`_escala_ficha_na_folha`, `_fecho_html_para_papel`, `odt_da_digitalizacao`); `tests/test_ri_certidao_digitalizacao.py`
- **Versao /saude oficial no momento:** **3.6.248** (antes=depois; hotfix pontual sem bump)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + DOCUMENTACAO)
- **Notas merge:** Padrão global DIGITALIZACAO (não só 3750): folha A4 21×29,7; margem 0,9 cm; capa tipográfica (título + subtítulo); 1 ficha/página centralizada cabendo na área útil; fecho sem sha256/frase técnica + carimbo selo + nome 1× sem traço. Reimprimir ODT da cert. 35/2026 (id 398) aplica. Backup: `ProgramData/CartorioGestao/backups_patch/hotfix_cert_repro_layout_20260929_*` e `tmp/hotfix_cert_repro_layout_20260929`. Preview: Downloads `preview_certidao_repro_3750_layout.odt` / `.pdf`.
- **nota_dev:** HOTFIX_OFICIAL: RI certidão reprográfica layout A4/capa/fecho (mat.3750)


**Regra:** qualquer alteracao em codigo em `C:\Program Files\CartorioGestao` (`*.py`, `templates/`, `static/`) deve ser registrada aqui **no mesmo dia** e espelhada no sandbox (`:8899`) antes de empacotar `.cgu`. Entradas **ABERTO** bloqueiam CGU ate merge no INSTALAR.

Documento canonico — manter identico em raiz do projeto (`CartorioGestao/docs/tecnico/`), INSTALAR e sandbox (`docs/tecnico/REGISTRO_HOTFIXES_OFICIAL.md`).

Plano de merge (Project Context): `internal/deploy/merge-hotfixes-prod-20260925.md`.

---


### HOTFIX-2026-09-30-02 - REURB tipo S/E/MISTO + isento auto REURB-S (prenot/atos RI)

- **Data/hora:** 2026-09-30 ~15:12 (America/Sao_Paulo)
- **Quem:** agente executor (Grok Bot) — pedido escrevente (cart3): isentar prenot 11579 + UI modalidade REURB
- **Motivo / problema:** Prenotação RI 11579 (REURB-S Quadra 1 Centro, mat. 120, Município) saiu cobrada R\$ 43,37 (selo PRENOT0000009N82OBV23EFJ8S70). Tela só tinha checkbox de prazo REURB-S, sem isento/motivo. escrevente pediu também opção S/E/misto em todos os atos RI com isento automático quando S.
- **Base legal:** Lei 13.465/2017 art. 13 §1º (isenção REURB-S); Dec. 9.310/2018 art. 53; CN TJMA arts. 436/452 (prazo 40 d.ú. só REURB-S).
- **Mudanças código:**
  - 	emplates/ri_protocolo.html: select 
eurb_tipo (não/S/E/MISTO) + campos isento/motivo; S marca isento + motivo Lei 13.465
  - 	emplates/ri_ficha.html: select 
eurb_tipo no lavrar ato (auto-isento S)
  - 
i_web.py: ler_isencao_do_form força isento+motivo em tipo S; prenotação grava 
eurb_tipo e prazo 40 só se S
  - 
i_schema.py: coluna 
i_protocolos.reurb_tipo TEXT
  - Script _regularizar_prenot_11579_isento.py (cancelar no Portal TJ -> reseal tentativa=2)
- **Dados 11579:** 
eurb_tipo=S gravado; selo cobrado AINDA ATIVO no TJ — reseal aguarda cancelamento humano no Portal
- **Versao /saude prod (8765):** **3.6.268**
- **Versao sandbox (:8899):** **3.6.268**
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM
- **Backup:** ProgramData/CartorioGestao/backups_patch/hotfix_reurb_tipo_* + hotfix_reurb_tipo_pf_pre_copy
- **Como verificar:** /registro-imoveis/protocolo — select Modalidade REURB; ficha mat. — select no lavrar; SELECT reurb, reurb_tipo, selo_prenotacao FROM ri_protocolos WHERE numero=11579; /saude 3.6.268
- **nota_dev:** HOTFIX_OFICIAL: REURB S/E/MISTO + isento auto S; prenot 11579 pendente reseal pós-cancelamento TJ


## HOTFIX-2026-09-29-09 — certidão inteiro teor: destaque R/AV

**Titulo:** Destaque visivel de R-01/AV-02 no miolo da certidao de inteiro teor (mat. 3247 / 33/2026)

- **Status:** ESPELHADO_SBX
- **Quando:** 2026-09-29 ~20:06 America/Sao_Paulo
- **Versao /saude prod (8765):** **3.6.260** (sem bump)
- **Causa:** `MIOLO_CERTIDAO_INTEIRO_TEOR` so imprimia `a.teor_odf`; a ficha ja tira o cabecalho do teor (`teor_sem_cabecalho_do_ato`), entao atos lavrados sem R/AV embutido no texto saiam na certidao sem rotulo. Acervo OCR (ex. mat 2005) ja trazia `R-1/2.005:-` em negrito no teor.
- **Correcao:** `html_com_destaque_rotulo_ato` prefixa `<b>R-01/3247:-</b>` no teor da certidao se ainda nao abrir com o rotulo; miolo usa `a.teor_certidao_odf`. Remontado corpo da cert 396 sem resealar.
- **Arquivos:** `ri_odt.py`, `ri_web.py`
- **Backup LIVE:** `ProgramData/CartorioGestao/backups_patch/hotfix_destaque_r_av_20260929-200606` + `backups/cert_396_3247_antes_destaque_r_av_20260929-200719`
- **Selo cert 396:** CERELE000000RO7S0H4FRGWRA610 (inalterado)
- **Espelho:** SANDBOX/sistema + SERVIDOR/INSTALAR_CARTORIO_GESTAO


## CGU 3.6.240 — 2026-09-28

**Titulo:** Ajuda #91–#95 + espelho sandbox (Notas, RCPN folha, RI CIB rural, busca atos)

- **Status:** APLICADO_OFICIAL
- **Quem:** agente bc-ce35cc9e-8d28-5474-af22-dfab778c7d73
- **Versao /saude prod (8765):** **3.6.240** (antes **3.6.239**)
- **Versao sandbox (:8899):** **3.6.240**
- **Drift pre-apply:** `hotfix_packaged` **12** (prod atras vs INSTALAR=sandbox); pos-apply **0**
- **Decisao:** pacote INSTALAR espelhado do sandbox; SQLite prod **nao** substituido
- **Backup:** `backup_pre_atualizacao_3.6.239_para_3.6.240_20260928_220119.zip` (`ProgramData/CartorioGestao/backups/`)
- **Pacote:** `CartorioGestao_3.6.240_20260928.cgu` SHA-256 `2b2967b14284368fe31a21d9d77de6c441083d29c9879cdb0f685d4607038b96`

---

## CGU 3.6.238 — 2026-09-28

**Titulo:** sandbox acumulado — L2/L3 certidão, Notas proc/ata, RCPN (óbito/nasc/casamento), HC casamento MVP

- **Status:** APLICADO_OFICIAL
- **Quem:** agente bc-a2a4b521-a372-5aec-9408-39b84555eef8
- **Versao /saude prod (8765):** **3.6.238** (antes **3.6.237**)
- **Versao sandbox (:8899):** **3.6.237** (reiniciar/apply para alinhar codigo; ensaios permanecem so no DB sandbox)
- **Drift pre-apply:** `hotfix_packaged` **9** (prod atras vs INSTALAR=sandbox); pos-apply **0**
- **Decisao:** pacote INSTALAR espelhado do sandbox; inclui `ri_certidao_emissao.py` e HC MVP
- **Backup:** `backup_pre_atualizacao_3.6.237_para_3.6.238_20260928_131808.zip` (+ copia em `docs/tecnico/backups/`)
- **Pacote:** `CartorioGestao_3.6.238_20260928.cgu` SHA-256 `b79947abe1a5abf7cad25ab56ba4836c99a92bd53085fd24e76796725e3ede62`
- **Hotfix absorvido:** HOTFIX-2026-09-28-01 (`ri_emitir_certidao`) — **NO_PACOTE**

---

## SBX 3.6.227 — 2026-09-27

**Titulo:** Livro 3 P2 — modelos ficha/certidão enriquecidos; ensaio registro #2 HIPOTECA

- **Status:** SANDBOX_ONLY (sem CGU)
- **Versao sandbox (:8899):** **3.6.227**
- **Versao INSTALAR / prod (8765):** **3.6.226** (espelho codigo; bump em `VERSAO.txt` + `app.py`)
- **Arquivos:** `atrib_certidao.py`, `livro3_modelos_ensaio.py`, `SANDBOX/ensaio_revisao_modular.py`, `tests/test_livro3_modelos_preview.py`

---

## RETROATIVO 2026-09-25

**Titulo:** 60 hotfixes prod — merge release **3.6.215** (sandbox + INSTALAR)

- **Status:** ESPELHADO_SBX (parcial empacotavel: 17 paths ainda prod≠par por features 214/P1)
- **Deteccao:** drift audit `summary.json` (prod vs INSTALAR vs sandbox)
- **Versao /saude prod (8765):** 3.6.202 — **nao alterada** neste merge
- **Versao sandbox (:8899):** 3.6.215 pos-merge
- **Backup:** `SANDBOX/sistema/backups_patch/pre_merge_214_20260925-114816/`
- **Drift hotfix_packaged:** 60 -> **17** (`tools/listar_drift_prod_instalar.py` pos-merge)
- **Drift INSTALAR≠sandbox (8):** **0** (espelho manual + pos-fix ri_odt/atribuicoes/ri_ficha)
- **Merge:** 50× MANTER_PROD (prod->SBX->INSTALAR); 10× MERGE_MANUAL (git merge-file base 3.6.193 payload)
- **Notas:** restante 17 = SBX/INSTALAR a frente de prod (ajuda id unificado, RI P1, app/ri_web/schema); CGU quando prod alinhar ou pacote 215.

---

## CGU 3.6.225 — 2026-09-26

**Titulo:** Livro 3 — editor de modelos (ficha/certidão) com prévia ao vivo (`/livro3/modelos`)

- **Status:** APLICADO_OFICIAL
- **Quem:** agente bc-ada960df-c0d3-5f30-b0c5-d7c4790ebe56 (delta pos-224)
- **Versao /saude prod (8765):** **3.6.225** (antes **3.6.224**)
- **Versao sandbox (:8899):** **3.6.225** (ja alinhado)
- **Drift pre-apply:** `hotfix_packaged` **28** (L3 + scripts `_*.py` locais); pos-apply **24** (so scripts `_*.py` fora do manifesto)
- **Decisao:** nao MANTER_PROD nos paths empacotaveis L3 — pacote INSTALAR=sandbox
- **Backup:** `backup_pre_atualizacao_3.6.224_para_3.6.225_20260926_183744.zip`
- **Inclui vs 224:** rotas `livro3_modelos`, `livro3_modelos_previa`; ensaio registro 1243 em `modelos_previa` para `RI_LIVRO3_*`; menu Livro 3 + atalhos na ficha
- **Arquivos:** `livro3_modelos_web.py`, `livro3_modelos_ensaio.py`, `modelos_previa.py`, `templates/livro3_modelos.html`, `templates/base.html`, `templates/atrib_livro3_ficha.html`, `tests/test_livro3_modelos_preview.py`

---

## CGU 3.6.224 — 2026-09-26

**Titulo:** apply oficial **3.6.217 -> 3.6.224** (Livro 2 RI 218–220, modelos 221–224)

- **Status:** NO_PACOTE (prod-only deltas substituidos pelo INSTALAR=sandbox)
- **Quem:** agente bc-b1fd0487-ac9c-5c81-b42b-14ef7d5646e8
- **Versao /saude prod antes:** 3.6.217 · sandbox :8899 **3.6.224**
- **Drift pre-apply:** `hotfix_packaged` **36** (`listar_drift_prod_instalar.py`); INSTALAR=sandbox **0** nos 8 paths monitorados
- **Decisao:** nao MANTER_PROD — pacote leva sandbox 218–224; scripts `_*.py` locais em Program Files permanecem fora do manifesto
- **Runtime paths afetados (ex.):** `app.py`, `ato_selado.py`, `modelos_*.py`, `ri_web.py`, `templates/base.html`, `templates/modelos.html`, `templates/ri_ficha.html`

---

## Template — nova entrada

Copie o bloco abaixo para cada hotfix ou lote coerente.

### HOTFIX-YYYY-MM-DD-NN — [titulo curto]

- **Data/hora:**
- **Quem:** (nome / agente bc-...)
- **Motivo / problema Ajuda:**
- **Paths:** (`arquivo1.py`, `templates/...`)
- **Versao /saude oficial no momento:**
- **Status:** ABERTO | EM_MERGE_SBX | ESPELHADO_SBX | DESCARTADO
- **INSTALAR espelhado?** SIM/NAO
- **Notas merge:** (conflito com 3.6.214? quem revisou?)

---

### HOTFIX-2026-09-28-01 — RI ficha 500: endpoint `ri_emitir_certidao` órfão

- **Data/hora:** 2026-09-28 ~10:40 (America/Sao_Paulo)
- **Quem:** agente bc-cd361aca (fix matrícula 5387 / 4.020)
- **Motivo / problema Ajuda:** `/registro-imoveis/5387` (e demais fichas RI) retornavam 500 — `BuildError` ao montar `url_for('ri_emitir_certidao')` porque decorators da rota POST `/certidao` ficaram acima dos helpers de origem dominial (regressão patch dominial/vintenária).
- **Paths:** `ri_web.py` (prod + INSTALAR espelho)
- **Versao /saude oficial no momento:** 3.6.234
- **Status:** ESPELHADO_SBX (INSTALAR espelhado; sandbox :8899 reiniciar se necessário)
- **INSTALAR espelhado?** SIM
- **Notas merge:** patch mínimo — mover `@app.route` + `@roles_required` para imediatamente antes de `def ri_emitir_certidao`. Testes: `test_ri_certidao_dominial_vintenaria.py`, `test_gratuidade_certidao_ri.py` (12 passed).
- **Status pos-CGU 3.6.238:** **NO_PACOTE** (oficial **3.6.238**)


### HOTFIX-2026-09-29-05 — RI certidão reprográfica: título + fecho protocolo

- **Data:** 2026-09-29 (America/Sao_Paulo)
- **Pedido:** escrevente / balcão — certidão da matrícula 3750 (reprográfica) sem cabeçalho de tipo e sem fecho de protocolo em aberto (padrão texto corrido 3.6.188)
- **Causa:** odt_da_digitalizacao imprimia só páginas digitalizadas + selo + nome; o corpo congelado (já com CERTIFICO ainda…) ficava só no livro e não ia ao papel. Título «CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA» não existia na via DIGITALIZACAO.
- **Versao /saude oficial no momento:** **3.6.248** (antes=depois; hotfix pontual sem bump)
- **Status:** ESPELHADO_SBX
- **Arquivos:** 
i_digitalizacao.py, 
i_web.py, 	ests/test_ri_certidao_digitalizacao.py
- **Notas merge:** (1) corpo_resumo_digitalizacao passa a gravar título + «Era o que nela continha.»; emitidor anexa clausula de prenotação + VALIDADE (espelho texto corrido). (2) odt_da_digitalizacao(..., corpo_html=): folha 1 = título do tipo; páginas = reprodução; folha final = fecho do corpo + selo + quem expediu. (3) Reimprimir ODT da cert. 35/2026 (id 398, mat. 3750) aplica o ajuste; reemitir só se quiser corpo novo com título/validade no livro. Backup: ProgramData/CartorioGestao/backups_patch/hotfix_cert_repro_3750_* e 	mp/hotfix_cert_repro_3750_20260929.
- **nota_dev:** HOTFIX_OFICIAL: RI certidão reprográfica título+fecho protocolo (mat. 3750)


### HOTFIX-2026-09-29-04 - RI inteiro teor/ficha: descasca envelope TX25 (mat. 2005)

- **Data/hora:** 2026-09-29 ~13:30 (America/Sao_Paulo)
- **Quem:** agente executor (escrevente - certidoes de inteiro teor desorganizadas; mat. 2005)
- **Motivo / problema Ajuda:** Certidoes de inteiro teor e fichas ACERVO saindo desorganizadas. Matricula **2005**. Causa: teor e-Oficio/TX Text Control como documento XHTML completo (`<?xml>`/`<html>`/`<body>`); `teor_seguro` (tela) ja extrai o body, mas `html_em_texto_corrido` (certidao + ODT ficha) nao — envelope no corpo e risca `separa-ato` duplicada ao detectar rotulo do ato.
- **Paths:** `ri_odt.py` (`miolo_html_do_documento` + inicio de `html_em_texto_corrido`); `tests/test_ri_certidao_texto_corrido_multi_selo.py`
- **Dados:** regenerado corpo certidao **34/2026** (id 397, mat. 2005); selo `CERELE000000BHBV2NV68TKIJ058` intacto; backup `ProgramData/CartorioGestao/backups/cert_397_2005_envelope_tx25_*`
- **Versao /saude oficial no momento:** **3.6.248** (hotfix pontual sem bump)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + DOCUMENTACAO)
- **Notas merge:** Padrao texto corrido 3.6.196/197; 9 testes OK. ~1507 mats / ~1239 atos com envelope — correcao no gerador (sem limpeza em massa). Certidoes ja emitidas com envelope no corpo congelado: regenerar corpo ou reemitir. Registro recuperado do rollback 3.6.248 + reentrada das hotfixes do dia.
- **nota_dev:** HOTFIX_OFICIAL: RI envelope TX25 texto corrido (mat.2005 / inteiro teor)

### HOTFIX-2026-09-29-03 - Livro 3-Aux: CNM na ficha (R-1651 + acervo)

- **Data/hora:** 2026-09-29 (America/Sao_Paulo)
- **Quem:** agente (escrevente / cart3 - R-1651)
- **Motivo / problema Ajuda:** CNM na ficha do Livro 3-Aux (R-1651 + acervo).
- **Status:** ESPELHADO_SBX (entrada reconstituida apos recuperacao do REGISTRO; detalhe completo pode estar em nota_dev/Ajuda do agente que aplicou)
- **Versao /saude oficial no momento:** **3.6.248** (ou adjacente no dia)
- **Nota recuperacao:** o arquivo `REGISTRO_HOTFIXES_OFICIAL.md` foi truncado por engano ao gravar HOTFIX-04; restaurado do rollback `20260929_121702_v3.6.248`. Esta entrada 03 existia no registro live (titulo confirmado) e foi recolocada de forma resumida.

### HOTFIX-2026-09-29-02 - Livro 3-Aux certidão: texto corrido (espelho RI)

- **Data/hora:** 2026-09-29 ~09:31 (America/Sao_Paulo)
- **Quem:** agente executor (escrevente - certidão Livro 3-Aux layout)
- **Motivo / problema Ajuda:** Certidão do registro auxiliar (Livro 3-Aux) saía com espaçamento excessivo (um parágrafo por linha via `texto_para_odf`). Pedido: texto corrido, sem espaços desnecessários, bem ajustado - mesmo padrão das certidões RI Livro 2 (inteiro teor: continuous text, separadores full-width, sem linha de assinatura à mão).
- **Paths:** `atribuicoes_web.py` (`_papel_da_certidao_do_livro3`)
- **Versao /saude oficial no momento:** **3.6.242** (antes=depois; hotfix pontual sem bump)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + DOCUMENTACAO)
- **Notas merge:** Em `_papel_da_certidao_do_livro3`: `texto_para_html` -> `html_em_texto_corrido` -> `html_para_odf` + `SEPARADOR_DE_ATO` entre blocos de ato; removido `<p></p>` vazio após o título. Layout só na impressão - teor congelado/sha256 não muda. Reimprimir ODT aplica o ajuste; reemitir só se quiser molde/teor novo. Backup: `ProgramData/CartorioGestao/backups_patch/hotfix_l3_cert_corrido_*`. Medido cert. id=4 (R-1651): 20->12 parágrafos; cert. id=3 (R-1243+AV): 20->10 + 1 separador.
- **nota_dev:** HOTFIX_OFICIAL: L3-Aux certidão texto corrido (espelho RI)

### HOTFIX-2026-09-29-01 - Livro 3 selo: protocolo 1..50 + código 16.45

- **Data/hora:** 2026-09-29 ~09:18 (America/Sao_Paulo)
- **Quem:** agente executor (escrevente cart3 - cédula 3-Aux R-1651)
- **Motivo / problema Ajuda:** Selagem do registro auxiliar **1.651** (ato 19) falhava com recusa do Tribunal «O tamanho do campo "protocolo" deve estar entre 1 e 50» (prenotação vazia -> `protocolo: ""`). Após preencher prenotação 11572, segunda recusa «Não foi encontrado um ato para o código informado» ao mandar subitem **16.45.23**; o selador aceita o cabeçalho **16.45** (medido no selo REGGAR da matrícula 3.247 / mesmo CCB, 28/09).
- **Paths:** `ra_selo.py`, `ra_selo_web.py`
- **Versao /saude oficial no momento:** **3.6.242**
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR)
- **Notas merge:** (1) `falta_para_selar(..., protocolo=)` recusa no balcão se vazio ou >50. (2) Bloqueio invertido: subitem `16.45.x` recusado com orientação a usar `16.45`; cabeçalho liberado. Backup: `ProgramData/CartorioGestao/backups_patch/hotfix_l3_protocolo_*`. Selo obtido: `REGGAR0000000JYSQQVO59M6V824`. Reiniciar :8765 para o processo Flask recarregar os .py.
- **nota_dev:** HOTFIX_OFICIAL: Livro3 selo protocolo+16.45 (R-1651)

### HOTFIX-2026-09-29-06 - Livro 3 ficha: teor do registro nao se repete sob ato R

- **Data/hora:** 2026-09-29 ~13:55 (America/Sao_Paulo)
- **Quem:** agente executor Cartorio Gestao (Grok Bot)
- **Motivo / problema Ajuda:** Ficha impressa do R-1651 (Livro 3-Aux, ra_registros.id=73) exibia **dois teores de registro** — o bloco `TEOR:` (`ra_registros.teor`) e de novo o corpo do ato R-1 em `ATOS:` (`ra_atos.teor` identico). Preferencia da casa: teores das fichas sem repetir cabecalhos/informacoes dos atos.
- **Paths:** `ra_ficha_odt.py` (`contexto`: se tipo R e ja ha teor no registro, omite corpo sob ATOS; mantem cabeca com selo/arquivamento). Mesma ideia da certidao L3 (`_bloco_atos_certidao_livro3` pula tipo R).
- **Versao /saude oficial no momento:** 3.6.248 (sem bump de versao — hotfix minimo)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (`SERVIDOR/INSTALAR_CARTORIO_GESTAO/ra_ficha_odt.py` + `SANDBOX/sistema/ra_ficha_odt.py`)
- **Backup:** `ProgramData/CartorioGestao/backups_patch/hotfix_l3_ficha_sem_dup_teor_20260929-134900/ra_ficha_odt.py`
- **Dados:** nenhum UPDATE em teor/selo; sem resealar. AV de outros registros (ex. R-1243) continuam com corpo sob ATOS.
- **Conferencia:** ODT R-1651 — 1x `TEOR:`, 1x «Dou fe», CNM `000000.3.0001651-61`; ATOS so cabeca R-1 + selos REGGAR… / ARQUIV…

### HOTFIX-2026-09-29-08 - Livro 3 ficha: carimbo do selo com QR

- **Data/hora:** 2026-09-29 ~14:50 (America/Sao_Paulo)
- **Quem:** agente executor Cartorio Gestao (Grok Bot)
- **Motivo / problema Ajuda:** Ficha impressa do Livro 3-Aux R-1658 (antes 1651, ra_registros.id=73) saia so com o codigo do selo em texto (selo REGGAR... / rquivamento ARQUIV...). Nao havia etiqueta/carimbo nem QR. Preferencia: selos na ficha como carimbos, na mesma estrutura da ficha do Livro 2, com QR. Sem resealar.
- **Causa:** 
a_ficha_odt.contexto montava a cabeca do ato em texto puro e montar_odt passava tudo por 	exto_para_odf. O gerador de QR (
i_odt.carimbo_compacto_odf / png_do_qr_do_selo) e selo_no_papel estavam inteiros; a ficha do Livro 3 nao os chamava. Dados em sd_selos tem texto completo (emolumentos); PNG do QR deriva do numero — nao faltava path de QR no banco.
- **Paths:** 
a_ficha_odt.py — carimbo do selo do ato e do arquivamento 16.39 logo abaixo da cabeca (HOTFIX-06 preservado: ato R nao repete o teor). Marcador @@CARIMBO_L3_<id>@@ trocado pela tabela ODF; PNG no pacote com nome unico por selo.
- **Versao /saude oficial no momento:** 3.6.248 (sem bump — hotfix minimo)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema/ra_ficha_odt.py + SERVIDOR/INSTALAR_CARTORIO_GESTAO/ra_ficha_odt.py)
- **Backup:** ProgramData/CartorioGestao/backups_patch/hotfix_l3_ficha_qr_20260929-145500/ra_ficha_odt.py
- **Dados:** nenhum UPDATE; sem resealar. Selos REGGAR0000000JYSQQVO59M6V824 e ARQUIV000000LSVDEIMCA1PMXM13 (22 fls).
- **Conferencia:** ODT R-1658 com 2 QR distintos (REGGAR + ARQUIV), 2x Total R\$, cabeca do ato R mantida, 1x TEOR, 1x Dou fe. Controle R-1243: AV-1 continua com teor e ganha carimbo+QR.

### HOTFIX-2026-09-29-08 — RI certidão TEXTO: etiquetas TX25 de selo -> carimbo lado a lado

- **Data/hora:** 2026-09-29 ~15:47 (America/Sao_Paulo)
- **Quem:** agente executor (balcão — cert. 35/2026 id 398 mat. 3750 selos empilhados)
- **Motivo:** Teor ACERVO (TX25/Word) traz selos numa tabela 2 colunas; `html_para_odf` achatava em Tab1+Tab2 empilhados (etiquetas uma embaixo da outra). Preferência: carimbo padrão da ficha, lado a lado; sem resealar.
- **Paths:** `ri_odt.py` (`carimbos_do_html_para_odf`); `tests/test_selos_tx25_lado_a_lado.py`
- **Versao /saude:** **3.6.248** (sem bump)
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM (SANDBOX/sistema + SERVIDOR/INSTALAR + LIVE)
- **Notas:** Detecta tabela-etiqueta TJMA (`Selo: CODIGO` + Poder Judiciário) e troca por `carimbo_do_selo_odf(..., por_fileira=2)` com QR. Reimprimir ODT da 35/2026 aplica. Backup: `ProgramData/CartorioGestao/backups_patch/hotfix_selos_layout_3750_*`. Preview: Downloads `preview_cert398_3750_selos_lado.odt`.
- **nota_dev:** HOTFIX_OFICIAL: RI certidão TEXTO selos TX25 -> carimbo lado a lado (mat.3750)



### HOTFIX-2026-10-04-01 — CNIB: referencia imutavel do acervo, cobertura e rotina diaria

- **Data/hora:** 2026-10-04T14:01:36 (America/Fortaleza)
- **Quem:** Codex, autorizado explicitamente pelo usuario neste chat.
- **Motivo / Ajuda:** #72; a origem mudava para CNIB no UPSERT e o inicio da recuperacao regredia de 19/03/2023 para 2016. A rotina diaria ficava desativada apos a primeira verificacao do processo.
- **Versao oficial:** 3.6.282; INSTALAR/sandbox 3.6.285. Excecao a divergencia de versoes autorizada pelo usuario em 04/10/2026; somente este hotfix minimo, sem CGU ou bump.
- **Paths:** cnib_atualizador.py, cnib_web.py, templates/cnib_central.html; tests/test_cnib_referencia_acervo.py nos espelhos.
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM
- **Mudancas:** referencia congelada em settings ou lida do acervo original; leitura parcial nao conclui janela; cobertura por faixa; download historico nao substitui consulta do dia; verificacao diaria por data; tela distingue ultima janela de cobertura completa.
- **Validacao:** 17 testes anteriores + 6 regressoes aprovados. Recuperacao: 18 meses, 556739 ordens novas, 36993 cancelamentos atualizados, 1052164 ordens; 44 meses consultados ate 04/10/2026; zero duplicatas, ordens perdidas ou canceladas reativadas.
- **Backup:** C:\Users\<usuario>\Downloads\cnib_recuperacao_20261004\hotfix_backup_20261004_140136
- **nota_dev:** HOTFIX_OFICIAL: CNIB referencia do acervo + cobertura + rotina diaria (#72).
- **Validacao em producao:** reinicio RESULTADO OK; novo PID 33164; /saude 3.6.282; tela CNIB HTTP 200, 44 meses consultados, zero pendentes. Prova: Downloads/cnib_hotfix_validacao.json.


### HOTFIX-2026-10-05-01 — CNIB: aviso vermelho de pendencias e nomes importados

- **Data/hora:** 05/10/2026 (America/Fortaleza).
- **Quem:** Codex, pedido do oficial neste chat; excecao de versao autorizada especificamente para este hotfix.
- **Versao oficial:** 3.6.282; INSTALAR/sandbox 3.6.285; sem CGU ou bump.
- **Paths:** ri_cnib.py, ri_web.py, cnib_atualizador.py, templates/ri_ficha.html; tests/test_cnib_aviso_pendente.py nos espelhos.
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM; alteracoes pontuais no template preservando as diferencas preexistentes do INSTALAR. Mudancas concorrentes de selagem/protocolo em ri_web.py do sandbox preservadas; os trechos CNIB conferidos em ambos os espelhos.
- **Mudancas:** aviso vermelho no alto da ficha, por documento ou nome; decisao ou minuta efetivamente lavrada baixa a ocorrencia; minuta A_REVISAR mantem o aviso. Busca por nome considera todas as partes. Atualizador preenche nome_norm; recuperacao do campo derivado nos dados existentes.
- **Dados operacionais:** 7 minutas A_REVISAR (20..26) e 7 tarefas ABERTA para escrevente id=3 (251..257), com partes e links de revisao. Sem lavratura ou numero consumido.
- **Validacao:** 23 testes anteriores + 4 regressoes aprovados; busca acentuada, aviso no alto da ficha, homonimo/cancelamento, manutencao em A_REVISAR e baixa apos lavratura.
- **Backup:** C:\Users\<usuario>\Downloads\cnib_recuperacao_20261004\aviso_backup_20261005_170102; DB anterior as minutas: Downloads/cnib_recuperacao_20261004/antes_minutas_tarefas.sqlite3.
- **nota_dev:** HOTFIX_OFICIAL: CNIB aviso vermelho de pendencias, nomes normalizados, 7 minutas e tarefas para escrevente.

- **Validacao final em producao:** reinicio RESULTADO OK; /saude 3.6.282; escrevente acessa 7 minutas e 7 tarefas (HTTP 200); alerta vermelho no alto das fichas por CPF/CNPJ e nome. Normalizacao concluida, zero nomes ausentes; 430 ocorrencias em 129 matriculas (7 documento, 423 nome). Prova: Downloads/cnib_aviso_validado.json.


### HOTFIX-2026-10-05-02 — CNIB: resolver ocorrencia diretamente no aviso da ficha

- **Data/hora:** 05/10/2026 (America/Fortaleza).
- **Quem:** Codex, pedido do oficial neste chat; excecao de versao autorizada para este hotfix pontual.
- **Versao oficial:** 3.6.282; INSTALAR/sandbox 3.6.285; sem CGU ou bump.
- **Paths:** ri_cnib.py, ri_web.py, templates/ri_ficha.html, templates/_cnib_decidir.html; tests/test_cnib_resolver_ficha.py nos espelhos.
- **Status:** ESPELHADO_SBX
- **INSTALAR espelhado?** SIM; preservadas diferencas preexistentes dos espelhos.
- **Mudancas:** botoes "Nao e a mesma pessoa" e "Ordem ja baixada", com evidencia/motivo obrigatorio e historico visivel (responsavel/data). Decisao local por matricula/ordem/pessoa, sem alterar a ordem global da CNIB ou atos lavrados; minuta vinculada A_REVISAR e preservada como DESCARTADA. Anotacao na tarefa vinculada, sem conclusao automatica. Dados da ocorrencia revalidados no banco, CSRF, duplo clique idempotente e protecao contra substituir decisao anterior.
- **Validacao:** 8 testes aprovados: tela, historico, homonimo/baixa, motivo, isolamento, minuta ligada/outras minutas, CSRF, ordem fabricada, decisao invalida, duplo clique e escape de HTML; 4 regressoes anteriores incluidas.
- **Backup:** C:\Users\<usuario>\Downloads\cnib_recuperacao_20261004\botoes_backup_20261005_184027
- **nota_dev:** HOTFIX_OFICIAL: CNIB resolver ocorrencia pelo aviso da ficha com motivo e historico.

- **Validacao final em producao:** reinicio RESULTADO OK, /saude 3.6.282; perfil escrevente acessa os dois botoes nas matriculas 1002 (nome) e 11 (documento), HTTP 200; 8 testes em bancos temporarios aprovados. Nenhuma decisao real registrada durante validacao. Prova: Downloads/cnib_botoes_validado.json.


## HOTFIX-2026-10-13-06 — Matrícula nova: reabrir rascunho e não perder dados na recusa
- Data: 13/10/2026 17:12 BRT · versão 3.6.290 (/saude ok antes e depois) · pedido: escrevente (17:09) «a 4022 em rascunho não ficou salva».
- Causa: o rascunho (id 27) estava COMPLETO em `rascunhos_de_tela`, mas `ri_nova_matricula` ignorava `?rascunho_id=` (o «abrir» de /rascunhos levava a um formulário vazio). Recusas de CIB/número faziam redirect e apagavam o formulário. CIB «00000000» passava como válido.
- Correção: `ri_web.py` (ri_nova_matricula) — GET lê `?rascunho_id=N` (tela ri_nova_matricula) e preenche o form; recusa de CIB/número ocupado re-renderiza a tela com os dados e a mensagem; CIB só de zeros = vazio nas matrículas de `cib_dispensado_matriculas`. `templates/ri_nova.html` — passa `rascunho_id` ao «salvar rascunho» (atualiza o mesmo, não duplica) e campo oculto `_rascunho_id_tela`.
- Aplicado sobre a cópia do Program Files (backups `*.bak-hf1306-20261013-171242`); espelho por patch idempotente (não copia o ri_web do INSTALAR/SANDBOX, que contém `import ri_onus_ia` não publicado).
- Status: ESPELHADO_SBX


## HOTFIX-2026-10-13-07 — Comprovante de gratuidade: vários arquivos por selo
- Data: 13/10/2026 17:42 BRT · versão 3.6.290 (/saude ok antes e depois) · pedido: escrevente (17:36).
- Antes: modelo já aceitava N anexos por selo (`attachments`, SELO_GRATUIDADE), mas a tela só tinha 1 arquivo por envio e o selo sumia da lista após o 1º, sem onde acrescentar/ver.
- Correção: `gratuidade_comprovante.py` (+`comprovados()`, `anexos()`); `gratuidade_comprovante_web.py` (upload com `getlist`, vários de uma vez, tudo-ou-nada; passa `feitos`); `templates/gratuidade_comprovantes.html` (`multiple`; seção «Já comprovados» com links /arquivo/<id>/ver e «Acrescentar»). Nada é apagado. Pendência continua saindo com ≥1 anexo.
- Backups `*.bak-hf1307-20261013-174214` no Program Files; espelho por patch idempotente.
- Status: ESPELHADO_SBX


## HOTFIX-2026-10-13-08 — Comprovantes de gratuidade: exibir matrícula e ato
- Data: 13/10/2026 ~18:45 BRT · versão 3.6.290 (/saude ok antes e depois) · pedido: escrevente (18:30) «de qual matrícula são esses selos?».
- Diagnóstico: vínculos CORRETOS (selos 26461-26465 ligados à mat. 4019 id 5381: abertura, R-01 ato 3751, AV-02 ato 3752); a tela só mostrava «IMOVEL ri atos 3751». TJ não registra matrícula no selo (informacoesLivro vazio).
- Correção (só exibição): `gratuidade_comprovante.py` +`rotulo()` («Mat. 4019 – R-01») em pendentes/comprovados; `templates/gratuidade_comprovantes.html` mostra o rótulo. Nenhum vínculo alterado.
- Backups `*.bak-hf1308-<ts>` no Program Files; espelho por patch idempotente.
- Status: ESPELHADO_SBX


## HOTFIX-2026-10-13-09 — Ficha impressa da 4023 sem o teor completo
- Data: 13/10/2026 21:23 BRT · versão 3.6.290 (/saude ok antes e depois) · pedido: escrevente (21:19).
- Causa: teor no banco íntegro (7.617 caracteres, termina em «Dou fé… Substituta»). O molde RI_FICHA, para ficha ESTRUTURADA com `descricao_perimetro`, imprime só «IMÓVEL: descrição» e campos, sem o teor (`usa_teor_como_miolo` só para ACERVO ou estruturada sem descrição).
- Correção: `ri_web.py` (contexto_ficha, só no papel `para_odt`): matrículas em `settings.ri_ficha_teor_no_papel` (["4023"]) imprimem o teor inteiro como miolo. Tela e certidão inalteradas.
- Backup `ri_web.py.bak-hf1309-20261013-212324`; espelho por patch idempotente (ri_onus_ia preservado no INSTALAR/SANDBOX).
- Status: ESPELHADO_SBX


## HOTFIX-2026-10-15-01 - Selo de abertura sumiu da ficha impressa da 4022
- Data: 15/10/2026 10:50 BRT - versao 3.6.292 (/saude ok antes e depois) - pedido: escrevente (15/10 10:48).
- Causa: efeito colateral do HOTFIX-2026-10-13-09. Para imprimir o teor, ele marcava a ficha como ACERVO no contexto do papel, e `selo_abertura_odf` e vazio para ACERVO. A 4022 esta selada (sd_selos 26941, MATRIC00000044UMOHV8O0H5P871, 13/10 17:23).
- Correcao: `ri_web.py` - flag `_teor_no_papel` nas matriculas de `ri_ficha_teor_no_papel`; o selo de abertura so e omitido no ACERVO de verdade. Carimbo e o mesmo dos atos (carimbo_compacto_odf: numero, valores, link e QR).
- Backup `ri_web.py.bak-hf1501-20261015-105047`; espelho por patch idempotente.
- Status: ESPELHADO_SBX


## HOTFIX-2026-10-16-01 - Notas: «atos do livro» (/notas/atos?livro_id=N) dava erro 500
- Data: 16/10/2026 11:12 BRT - versao 3.6.292 (/saude ok antes e depois) - pedido: escrevente (16/10 11:09).
- Causa: `notas_atos.html` (linha 13) usa `TIPOS_LIVRO` no aviso «Atos do livro N — <tipo>», mas `notas_web.notas_atos` nao passava a variavel ao template: `jinja2.exceptions.UndefinedError: 'TIPOS_LIVRO' is undefined` (servidor.log, 15/10/2026). Notas -> Livros -> atos do livro caia.
- Correcao: `notas_web.py` - `TIPOS_LIVRO=TIPOS_LIVRO` no `render_template("notas_atos.html", ...)`. Uma linha; nenhuma regra mudou.
- Backup `notas_web.py.bak-hf1601-20261016-111229`; reinicio controlado (reiniciar_servidor.ps1), /saude ok 11:13.
- Espelho: INSTALAR por patch idempotente; SANDBOX ja tinha a mesma correcao (feita pelo Projeto em 15/10/2026).
- Status: ESPELHADO_SBX

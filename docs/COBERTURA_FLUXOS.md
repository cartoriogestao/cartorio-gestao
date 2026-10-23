# Cobertura dos fluxos — do protocolo à certidão

Pedido do oficial (20/10/2026): «quero que seja possível do protocolo à
certidão. Minha maior preocupação é que TODOS os atos precisam ter uma certidão
adequada» — e «TERMO E CERTIDÃO». Cada atribuição tem a sua seção, escrita pelo
lote dela: ato × etapa, com **✓** coberto por teste pelas telas, **✗** sem teste
e **⚠** defeito (o teste está marcado `xfail(strict=True)` com o motivo, ou o
defeito foi consertado no lote — está dito).

Etapas: protocolo do caixa → pagamento / depósito / gratuidade → prática do ato
→ termo → selo → livro/folha/número → certidão fiel ao termo.

## Registro Civil das Pessoas Naturais (LT01)

Testes: `tests/test_fluxo_rcpn.py` (pelas telas, com login, CSRF, protocolo e
selador de mentira) e `tests/test_requisitos_rcpn.py` (a matriz da lei contra
os modelos da casa — ver `docs/REQUISITOS_LEGAIS.md`). Inventário lido do
código: espécies em `rc_assento.SERIE_DA_ESPECIE`, caminhos e itens do selo em
`ato_selado.SEGMENTO_DA_ESPECIE`/`CODIGO_DO_REGISTRO_DO_CIVIL`/
`CODIGO_DO_ATO_DO_CIVIL`, modelos em `rc_termo.MODELO_DA_ESPECIE`,
modalidades da certidão em `rc_certidao_inteiro_teor`, molde do papel em
`rc_certidao_odt.ESPECIES_QUE_O_MOLDE_SERVE`.

Colunas: **Prot.** protocolo do caixa · **Pag.** pagamento, depósito ou
gratuidade · **Ato** prática do ato pela tela · **Termo** o texto lavrado no
livro · **Selo** · **L/F/N** livro, folha e número (e a matrícula) ·
**Certidão** a certidão fiel ao termo (teor + papel ODT/PDF) · **—** não se
aplica.

### Registros (assentos)

| Ato (série, item do TJ) | Prot. | Pag. | Ato | Termo | Selo | L/F/N | Certidão |
|---|---|---|---|---|---|---|---|
| Nascimento (Livro A, 14.a isento) | — (gratuito, LRP art. 30) | ✓ gratuidade da lei, sem lançamento | ✓ · ✓ LD01: duas gavetas de testemunha; o município do local, com o da serventia escrito | ✓ art. 54 · ✓ LD01: testemunhas do parto domiciliar (`nasc.testemunhas`) · ✓ LD01: gêmeo e a ordem (`nasc.gemeo`) | ✓ isento, folha no `papelMoeda` | ✓ + matrícula | ✓ 1ª via com o selo e a folha do registro · ✓ LD01: o papel diz o município, e não a rua (`test_o_papel_da_certidao_de_nascimento_diz_o_municipio_e_nao_a_rua`, `test_o_municipio_que_o_balcao_escreve_e_o_que_o_papel_imprime`) |
| Óbito (Livro C, 14.c isento) | — | ✓ | ✓ | ✓ art. 80 / CN-MA 255 · ✓ LD01: no feminino (`test_o_termo_de_obito_de_uma_falecida_concorda_no_feminino`) · ✓ LD01: sexo, idade e cor, natureza da morte, qualificação dos pais (matriz) · ✓ consertado: «pessoa não identificada» | ✓ | ✓ | ✓ breve relato · ✓ LD01: eleitor, bens e filhos no breve relato (`cert.obito_eleitor_bens_filhos`) · ✓ consertado: papel com cônjuge, bens e filhos, lidos com a régua do termo (`test_o_papel_e_o_termo_leem_a_marca_de_bens_e_filhos_do_mesmo_jeito`) · ✓ LD01: papel com o município do falecimento (`test_o_papel_da_certidao_de_obito_traz_o_municipio_do_falecimento`) |
| Natimorto (Livro C-Auxiliar, 14.d isento) | — | ✓ | ✓ | ✓ LD01: «nasceu morta», com a Declaração de Óbito (`test_o_termo_de_natimorto_declara_que_a_crianca_nasceu_morta`) | ✓ | ✓ | ✓ breve relato · ✓ LD01: papel próprio, `certidao_natimorto_modelo.odt` (`test_a_certidao_de_natimorto_sai_em_papel`) |
| Casamento com habilitação DESTA casa (Livro B, 14.1.1) | ✓ | ✓ | ✓ LD01: o edital se registra no Livro D ao ser publicado, e a habilitação chega ao HABILITADO com o selo (`test_casamento_pela_habilitacao_desta_casa_vai_do_protocolo_a_certidao`) · ✓ o casamento lavrado a partir dela não compra selo | ✓ LD01: a data dos proclamas e a relação dos documentos da habilitação (`cas.proclamas_desta_casa`, `test_o_casamento_lavrado_pela_habilitacao_desta_casa_traz_os_proclamas`) | ✓ o da habilitação (14.1.1), com livro/folha/termo do Livro D | ✓ | ✗ (2ª via, a mesma do casamento de fora) |
| Casamento com habilitação de OUTRA serventia (Livro B, 14.1.6) | ✓ | ✓ pago no caixa | ✓ · ✓ LD01: a segunda testemunha | ✓ art. 70 · ✓ LD01: as duas testemunhas, qualificadas (`test_o_casamento_registra_as_duas_testemunhas`) · ✓ LD01: a data da celebração (`test_o_termo_de_casamento_traz_a_data_da_celebracao`) · ✓ LD01: pais e testemunhas qualificados (matriz) | ✓ comprado no registro, cobertura do protocolo | ✓ | ✓ 14.5.1 pelo protocolo, folha nova, papel com selo |
| Casamento religioso com efeito civil (B-Auxiliar) | ✗ | ✗ | ✗ | ✗ (mesmo modelo do civil) | ✗ | ✗ | ✗ |
| Conversão de união estável em casamento | ✗ | ✗ | ✗ (habilitação `CONVERSAO`, mesmo defeito do Livro D) | ✗ | ✗ | ✗ | ✗ |
| Proclamas (Livro D, 14.1.2) | — (desta casa: o 14.1.1 da habilitação) | — | ✓ LD01: o edital da habilitação desta casa se registra sozinho no Livro D, uma vez só; o registro não compra selo à parte (`test_o_registro_do_edital_no_livro_d_nao_compra_selo_a_parte`) · ✗ proclama recebido de outra serventia, sem teste | ✓ LD01: teor do registro com a época da publicação e os documentos (CN-MA art. 267) | ✓ o da habilitação, anotado no registro | ✓ | ✓ LD01: edital com estado civil, filiação e cidade do domicílio (`edital.proclamas`) |
| Livro E — emancipação, interdição, ausência, tutela (14.2), união estável (14.8), opção de nacionalidade (14.3.2) | ✓ | ✓ pago | ✓ | ✓ arts. 89 a 94-A (`test_o_registro_do_livro_e_vai_do_protocolo_ao_termo_selado`, 6 espécies) | ✓ sem folha | ✓ | ✓ LD01: breve relato com a espécie, o título, o curador/tutor/companheiros e os limites, e papel próprio (`certidao_livro_e_modelo.odt`) — `test_a_certidao_do_livro_e_traz_o_que_o_termo_registra`, 6 espécies |
| Livro E — «Outro registro» (`OUTRO`) | ✗ | ✗ | ⚠ sem caminho de selo (`ato_selado.SEGMENTO_DA_ESPECIE` o deixa de fora): lavrado por pessoa, o selo falha e o assento é cancelado — lido no código, sem teste | ✗ | ⚠ | ✗ | ✗ |
| Traslado de assento lavrado no exterior | ✗ | ✗ | ✗ não modelado (não há espécie; CN-MA arts. 307 a 327) | ✗ | ✗ | ✗ | ✗ |
| Registro tardio de nascimento | — (gratuito, como o nascimento) | ✗ sem teste próprio | ✓ LH05 (hotfixes do servidor de 21/10/2026): a marca, o número do requerimento e a segunda testemunha pela tela, e a lavratura recusa o tardio sem as duas (art. 249, II) (`test_o_tardio_lavrado_pela_tela_leva_a_marca_as_testemunhas_e_a_frase`) · o requerimento preenchido para assinar, da conferência e da tela de preencher (`test_a_conferencia_traz_o_requerimento_preenchido`, `test_o_requerimento_se_imprime_da_tela_de_preencher`) · a leitura monta o nascimento sem DNV (`test_com_a_marca_o_tardio_se_monta_sem_dnv_e_sem_requerimento`) | ✓ LH05: «Registro lavrado fora do prazo legal…» com o requerimento e as testemunhas, ou a dispensa calculada (`nasc.tardio`, `nasc.tardio_dispensa`) | ✗ sem teste próprio | ✗ sem teste próprio | ✗ |
| Gêmeos (amarração dos dois assentos) | ✗ | — | ✗ (`/rcpn/gemeos`) | ✓ LD01: o parto múltiplo do balcão e a ordem vão ao termo (`nasc.gemeo`) | — | ✗ | ✗ |

### Lançamentos no assento e certidões

| Ato | Prot. | Pag. | Ato | Termo | Selo | L/F/N | Certidão |
|---|---|---|---|---|---|---|---|
| Averbação (14.4.1) | ✓ | ✓ | ✓ com a natureza | ✓ teor com quem lavrou e o selo | ✓ `/averbacao` | ✓ no espaço do assento | ✓ entra na 2ª via · ✓ LD01: com a inscrição do art. 21, no teor e no papel (`cert.inscricao_do_art_21`) |
| Anotação (14.7) | ✓ | ✓ | ✓ | ✓ | ✓ `/anotacao` | ✓ | ✓ entra na 2ª via |
| Retificação (14.10) | ✓ | ✓ | ✓ com fundamento | ✓ | ✓ `/retificacao` | ✓ | ✓ entra na 2ª via |
| Averbação gratuita (hipossuficiência) | — | ✓ selo GRATUITO com motivo, PDF guardado e a pendência some | ✓ | ✓ | ✓ | ✓ | — |
| Averbação de CPF (art. 347) | — | ✓ (testes próprios: `test_rc_cpf_casamento_web.py`) | ✓ | ✓ | ✓ | ✓ | ✗ neste lote |
| Retificação administrativa (processo, `retificacao_rcpn`) | ✗ | ✗ | ✗ ponta a ponta (há teste de módulo) | ✗ | ✗ | ✗ | ✗ |
| Anotações pendentes e as que vêm da CRC | ✗ | — | ✗ neste lote (há `test_rc_anotacao*.py`) | ✗ | ✗ | — | ✗ |
| Certidão em breve relato, 1ª via (nascimento, óbito, natimorto) | — | ✓ gratuita | ✓ | — | ✓ o do registro, sem selo novo | ✓ | ✓ fiel ao termo (teor e papel) |
| Certidão em breve relato, 2ª via (14.5.1) | ✓ | ✓ | ✓ | — | ✓ `/segunda-via` | ✓ | ✓ papel com serventia, CNS, oficial, selo, consulta, QR e o valor pela etiqueta do selo |
| Certidão de inteiro teor, texto (14.5.6) | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ reproduz o termo palavra por palavra |
| Certidão de inteiro teor, reprográfica / da digitalização | ✗ | ✗ | ✗ neste lote (há `test_rc_digitalizacao.py`) | — | ✗ | ✗ | ✗ |
| Certidão de habilitação | ✓ (protocolo 14.1.1) | ✓ | ✓ LD01: expede, com o Livro D registrado | — | ✓ 14.1.1, um selo só (a unidade do protocolo gasta pela habilitação) | — | ✓ modelo conferido na matriz (`cert.habilitacao`) |
| Certidão negativa | — | — | ⚠ não existe no RCPN: o contrato do selador tem `/certidao-negativa`, a casa não tem rota (CNN art. 238; CN-MA art. 385) | — | — | — | ✗ |
| Certidão eletrônica (CRC) | ✗ | ✗ | ✗ fora deste lote (há `test_rc_certidao_eletronica_*.py`) | — | ✗ | ✗ | ✗ |

### Consertado no LD01 (21/10/2026), e o que ficou

«Corrija tudo» — o oficial, sobre a lista dos `xfail` do LT01. Os 40 testes
(13 linhas da matriz em `test_requisitos_rcpn.py`, nos dois testes de cada
linha, e 14 em `test_fluxo_rcpn.py`) passam sem a marca; o que cada um
consertou está dito no próprio teste. Testes novos do mesmo lote, pelas telas:
o município que o balcão escreve é o que o papel imprime; o registro do edital
no Livro D não compra selo à parte (o caminho de erro do selo); o edital
publicado antes do LD01 se registra ao habilitar; o casamento lavrado pela
habilitação desta casa traz os proclamas e os documentos.

Ficou para depois, e não é defeito da lista: a segunda testemunha não se corrige
pela ficha do assento (`atrib_rcpn_editar.html` tem uma gaveta); os moldes novos
(natimorto e Livro E) não estão no catálogo da tela de Modelos
(`modelos_moldes.MOLDES`), e por isso a casa ainda não os ajusta por lá; o breve
relato do nascimento não tem a linha «MUNICÍPIO DE NASCIMENTO» que o papel tem.
As perguntas ao oficial estão em `relatorios/LD01.perguntas.md`.

Observado no caminho e sem teste próprio: o **rascunho para o declarante**
da tela de conferência (`rcpn_conferencia.html`) imprime «None» nos campos que
não foram preenchidos («Cor/raça: None», «nasc. None, None, None, CPF None»).

As duas linhas do RCPN que a seção do caixa (LT06) deixou para este lote estão
cobertas aqui, pelas telas: a **certidão paga (14.5.1), 2ª via**, com o
protocolo pago e a folha de segurança, em
`test_segunda_via_e_inteiro_teor_saem_pagos_pelo_protocolo`; e a **gratuidade
presumida** do nascimento, do óbito e do natimorto (selo ISENTO pelo item da
lei, 14.a, 14.c e 14.d, e nenhum lançamento no caixa) nos três testes «do
balcão» de cada espécie.

## Caixa e protocolo geral (LT06)

Transversal: o caixa não lavra ato de livro. O que ele **escreve** na casa é o
lançamento (`cx_lancamentos`, um por serviço, com os fundos) e a linha do Livro
de Controle de Depósito Prévio; o que **sai com o cliente** é o recibo, o
comprovante de recepção e o orçamento. «Termo» e «certidão» do caixa são esses
dois lados, e têm de bater. Testes: `tests/test_fluxo_caixa.py` (pelas telas,
login + token, aparelho selador de mentira sem o protocolo pronto da bancada) e
`tests/test_requisitos_caixa.py` (a matriz de `docs/REQUISITOS_LEGAIS.md`).

### O que o caixa faz (inventário lido em `caixa_web.py`, `caixa_protocolo.py`, `caixa_depositos.py`, `caixa_schema.py`, `livro_deposito_previo.py`, `nfse_web.py`, `gratuidade_comprovante_web.py`)

| Ato do caixa | Rota | Termo (o que fica escrito) | Papel / certidão | Teste |
|---|---|---|---|---|
| Abrir protocolo (`AAAA.MM.N`, contato obrigatório) | `POST /caixa/protocolos` `acao=novo` | `cx_protocolos` | — | ✓ `test_o_balcao_abre_o_protocolo_com_o_numero_do_mes_e_o_contato`, `test_o_segundo_protocolo_do_mes_ganha_o_numero_seguinte` |
| Comprovante de recepção | `POST /caixa/protocolos/<id>/recepcao` | `recepcao_em` | `CAIXA_RECEPCAO` (.odt) | ✓ `test_o_comprovante_de_recepcao_diz_o_que_entrou_no_balcao` + matriz |
| Acrescentar item da tabela (valor fixo) | `POST …/itens` `acao=acrescentar` | `cx_protocolo_atos` (fundos × quantidade) | — | ✓ `test_o_item_vem_da_tabela_do_tribunal_com_os_fundos_separados` |
| Acrescentar item pela faixa (valor do negócio, 16.31) | idem, `tabela` + `base_calculo` | idem | — | ✗ (coberto por `test_garantia_em_varios_imoveis.py`, fora da fila do LT06) |
| Quitar um item / quitar todos | `POST …/itens` `acao=quitar` / `quitar_todos` | `cx_lancamentos` (um por item, `origem=PROTOCOLO`, número, hash) | — | ✓ `test_quitar_lanca_cada_item_no_caixa_e_o_protocolo_fica_pago`, `test_sem_caixa_aberto_o_item_nao_se_quita` |
| Recibo do atendimento | `POST /caixa/protocolos/<id>/recibo` → `/caixa/recibo/<id>/odt` | `cx_recibos` (teor congelado + hash) | `CAIXA_RECIBO` | ✓ `test_o_recibo_do_atendimento_e_fiel_ao_que_entrou_no_caixa`, `test_o_mesmo_dinheiro_nao_sai_em_dois_recibos`, `test_a_reimpressao_do_recibo_sai_com_o_mesmo_teor`, `test_sem_servico_pago_nao_ha_recibo` |
| Recibo de um lançamento | `POST /caixa/recibo/<lancamento_id>` | `cx_recibos` | `CAIXA_RECIBO` | ✓ — era ⚠, **consertado no LT06**: `test_o_recibo_de_um_lancamento_discrimina_so_o_que_ele_pagou` |
| Orçamento / mero cálculo | `GET /caixa/protocolos/<id>/orcamento` | — | `CAIXA_ORCAMENTO` + peça do aviso | ✓ `test_o_orcamento_de_mero_calculo_diz_que_nao_e_ato` + matriz |
| Estorno | `POST /caixa` `acao=estornar` | lançamento `ESTORNO` + original marcado; item volta a «a pagar» | — | ✓ `test_o_estorno_exige_motivo_desfaz_a_quitacao_e_deixa_o_rastro` |
| Encerrar / reabrir protocolo | `POST /caixa/protocolos/<id>` `acao=encerrar/reabrir` | `situacao`, `encerramento_motivo` | — | ✓ `test_protocolo_com_dinheiro_dentro_nao_se_encerra`, `test_o_protocolo_sem_servico_se_encerra_com_motivo_e_reabre` |
| Depósito prévio: criar, usar, devolver | `POST /caixa/depositos` `acao=novo/usar/devolver` | `cx_depositos` (com o orçamento congelado e o lançamento) + lançamento + `audit_logs` | — | ✓ `test_o_deposito_previo_entra_no_caixa_e_e_consumido_no_protocolo`, `test_a_devolucao_do_deposito_sai_da_gaveta_com_o_motivo`, `test_o_protocolo_do_orcamento_que_nao_existe_e_recusado_sem_gravar` (LD06) |
| Depósito pagando o item (quadro «Selo e caixa») | `POST /selo/cobertura/deposito` | `cx_deposito_usos`, item quitado | — | ✓ `test_o_deposito_que_pagou_o_item_pelo_quadro_do_selo_aparece_no_livro` |
| Livro de Controle de Depósito Prévio (art. 198) | `GET /livros-obrigatorios/deposito-previo` | — | o livro (tela) | ✓ I–V `test_o_livro_de_deposito_previo_traz_as_seis_indicacoes_do_art_198` + matriz; ✓ VI — era ⚠, **consertado no LD06**: `test_o_deposito_guarda_o_orcamento_completo_do_art_198_vi`, `test_o_deposito_sem_orcamento_entra_avisado_e_o_livro_aponta_a_falta` |
| Recibo do depósito prévio (art. 197) | `POST /caixa/recibo/<lançamento do depósito>` | `cx_recibos` (o orçamento congelado do depósito) | `CAIXA_RECIBO` («DISCRIMINAÇÃO ORÇAMENTÁRIA») | ✓ — era ⚠, **consertado no LD06**: `test_o_recibo_do_deposito_previo_traz_o_orcamento_discriminado`, `test_o_deposito_com_o_protocolo_do_orcamento_guarda_cada_item_com_os_fundos` |
| «Usar» o depósito no protocolo | `POST /caixa/depositos` `acao=usar` | baixa o saldo, quita os itens inteiros que o valor cobre (`cx_deposito_usos` + `quitado_por`), lança o uso | — | ✓ — era ⚠, **consertado no LD06**: `test_usar_o_deposito_no_protocolo_quita_o_item`, `test_usar_quita_so_os_itens_inteiros_que_o_valor_cobre_e_avisa_o_resto`, `test_o_item_pago_pelo_deposito_nao_se_cobra_de_novo_nem_se_reabre`, `test_o_selo_do_item_pago_pelo_usar_nao_debita_o_deposito_outra_vez`; `test_usar_nao_paga_com_o_deposito_o_item_que_o_outro_clique_ja_quitou` (`test_caixa_dois_cliques.py`); `test_usar_e_o_selo_no_mesmo_item_nao_pagam_duas_vezes` (`test_selo_e_caixa.py`) |
| NFS-e (desligada de fábrica) | `POST /caixa/nfse/recibo/<id>/emitir` | nenhuma nota | — | ✓ `test_a_nfse_nasce_desligada_e_o_recibo_nao_vira_nota_sozinho` |
| Fechar o caixa / conferir (outra pessoa) | `POST /caixa` `acao=fechar/conferir` | `cx_caixas` (`fechado_por`, `conferido_por`) | — | ✓ `test_o_caixa_se_fecha_por_quem_atendeu_e_se_confere_por_outro` |
| Lançamento avulso, edição, exclusão | `POST /caixa` `acao=lancar/editar/excluir` | `cx_lancamentos` (`historico`) | — | ✗ (cobertos por `test_caixa_*`, fora da fila) |
| Importar do E-Ofício | `POST /caixa/importar` | — | — | ✗ (ambiente: pasta exportada) |

### Selo pago × caixa e gratuidade, em cada atribuição

| Atribuição | Ato medido (item) | Sem protocolo / sem pagamento | Com protocolo pago | Gratuidade | Teste |
|---|---|---|---|---|---|
| Notas | reconhecimento de firma (13.17.2) | ✓ ato não lavrado, a tela leva ao quadro «Selo e caixa» | ✓ sela e gasta 1 unidade; cobertura `ITEM_PAGO` confirmada | — | `test_notas_o_reconhecimento_de_firma_so_sela_com_o_protocolo_pago` |
| Registro de Imóveis | certidão de inteiro teor (16.24.4) | ✓ certidão cancelada, com o quadro na frase | ✓ sai selada | ✓ «isento» sem motivo não escapa da trava | `test_ri_a_certidao_de_inteiro_teor_so_sela_com_o_protocolo_pago`, `test_marcar_isento_sem_o_motivo_nao_escapa_da_trava_do_selo_pago` |
| Protesto | certidão por nome (17.5.1) | ✓ item não pago: certidão cancelada, e o item volta ao protocolo | ✓ com o protocolo em atendimento; ✓ só com o protocolo escolhido na certidão (era ⚠, **consertado no LD06**) | — | `test_protesto_a_certidao_so_sela_com_o_item_pago`, `test_protesto_o_protocolo_escolhido_na_certidao_basta_quando_o_item_esta_pago` |
| RTD/RCPJ | certidão (15.10.1) | ✓ item não pago: certidão cancelada, e o item volta ao protocolo; ✓ protocolo sem item disponível: certidão cancelada, com o porquê | ✓ pago antes: sai selada; ✓ pago depois da recusa: sai selada (era ⚠, **consertado no LD06**) | — | `test_rtd_a_certidao_com_o_item_pago_sai_selada`, `test_rtd_a_certidao_paga_depois_da_recusa_sai_selada`, `test_rtd_o_protocolo_sem_item_disponivel_nao_deixa_a_certidao_sair_sem_selo` |
| Notas | certidão (13.12.1) | ✓ selo que não sai: certidão cancelada, e o item volta ao protocolo (o mesmo defeito do RTD, **consertado no LD06**) | — | — | `test_notas_a_certidao_cancelada_devolve_o_item_ao_protocolo` |
| RCPN | averbação do CPF (gratuita por lei) | ✓ selo isento sai sem protocolo | — | ✓ a barra cobra o PDF (comprovante + certidão) e some ao guardar | `test_rcpn_o_selo_gratuito_sai_sem_caixa_e_a_barra_cobra_o_comprovante` |
| RCPN | certidão paga (14.5.1), 2ª via | ✗ | ✗ | gratuidade presumida (nascimento/óbito): ✗ pela tela (coberta em unidade por `test_selo_e_caixa.py`) | — (fica com o LT01: o assento e a folha de segurança são do fluxo do RCPN) |

### Defeitos

1. **Consertado — recibo de um lançamento discriminava o protocolo inteiro.**
   `caixa_web.caixa_recibo` listava todos os itens do protocolo, pagos ou não,
   e somava os fundos de todos: «a importância de R$ 6,21» com a discriminação
   de R$ 51,57. Agora lista só os itens que aquele lançamento quitou; sem item
   (lançamento do ato, avulso), os fundos saem do próprio lançamento — o
   recibo do atendimento inteiro continua sendo o do protocolo. (CN-MA art.
   87, IX e XVI; LRP art. 14, parágrafo único.)
2. **Consertado — o Livro de Depósito Prévio não via o débito do selo.** O selo
   e o quadro «Selo e caixa» quitam o item com o depósito
   (`caixa_depositos.pagar_item`) e o rastro vai para `cx_deposito_usos`; o
   livro só lia `audit_logs` e mostrava a conversão como dinheiro que «saiu do
   saldo sem uso nem devolução». O livro passou a ler `cx_deposito_usos`, com o
   item e o ato (art. 198, IV). Só leitura.
3. **Consertado no LD06 — depósito sem orçamento (CN-MA arts. 197 e 198, VI).**
   O depósito guarda o orçamento CONGELADO no dia (`cx_depositos.orcamento`):
   os itens a pagar do protocolo que ele aponta (campo novo «Protocolo do
   orçamento» na tela) ou, sem protocolo, o serviço pela tabela vigente — a
   mesma conta do protocolo (`emolumentos.calcular_item`) —, cada item com os
   emolumentos e os quatro fundos. O recibo do lançamento do depósito
   (`cx_depositos.lancamento_id`) traz a «DISCRIMINAÇÃO ORÇAMENTÁRIA» e diz
   que é orçamento, e não pagamento de ato; o livro mostra o orçamento por
   extenso na coluna VI. Depósito sem nenhum dos dois continua entrando (o
   tipo é opcional, decisão do oficial de 17/09/2026), com aviso na tela e a
   falta no livro — pergunta 1 de `relatorios/LD06.perguntas.md`.
4. **Consertado no LD06 — «usar» o depósito não quitava o item.** O «usar» com
   o protocolo quita os itens a pagar que o valor cobre INTEIROS, na ordem do
   protocolo, pelo mesmo débito do quadro «Selo e caixa» (`debitar` +
   `quitar_o_item`, com o rastro em `cx_deposito_usos`); o resto é o uso de
   sempre, e a tela avisa o item que continua a pagar. Os itens se prendem
   ANTES do depósito, na ordem do selo. Nada de item pago duas vezes: o caixa
   recusa cobrar o item já quitado (`cobrar_item_do_protocolo`) e «reabrir» o
   item pago pelo depósito. CN-MA art. 202. As escolhas de dinheiro que ficaram
   (valor que não fecha com itens, desfazer o uso, receita com os fundos) são
   as perguntas 2 a 4.
5. **Consertado no LD06 — RTD/RCPJ: certidão paga depois da recusa saía sem
   selo e sem aviso.** A certidão cancelada pelo selo devolve ao protocolo o
   item que a tela ligou a ela (`caixa_protocolo.soltar_itens_do_ato`); e a
   certidão pedida com um protocolo sem item disponível é cancelada com o
   porquê, em vez de sair sem selo calada (CN-MA art. 130, § 2º). O mesmo
   conserto vale para a certidão das Notas, que tinha o mesmo defeito.
6. **Consertado no LD06 — Protesto: o protocolo escolhido na certidão não
   ligava o item.** A certidão do Protesto liga os itens do protocolo escolhido
   antes do selo, como a do RTD, e a busca que veio no protocolo continua
   saindo por ela (`_itens_ligados_ao_ato`).

### O que ficou de fora, e por quê

- A certidão paga do RCPN pela tela (assento + folha de segurança) — é o fluxo
  do LT01; a trava do selo é a mesma (`obter_selo`), medida aqui nas outras
  quatro atribuições.
- A gratuidade presumida (nascimento, óbito, natimorto) pela tela — o registro
  é o fluxo do LT01; a regra está em `test_selo_e_caixa.py`
  (`test_registro_de_nascimento_nao_vira_pendencia`).
- O diferimento do Protesto («a posteriori», CRA) pela tela: a rota
  `/selo/cobertura/diferir` existe; o diferimento da tela do título
  (`pt_emolumentos_diferidos`) não conta para a trava — é do LT04.
Cada atribuição tem a sua seção, escrita pelo lote que a mediu: o inventário
dos tipos de ato, lido no código, e, para cada um, as etapas do balcão com o
teste que as cobre.

## Tabelionato de Notas (LT02)

Pedido do oficial, 20/10/2026: «quero que seja possível do protocolo à
certidão. Minha maior preocupação é que TODOS os atos precisam ter uma
certidão adequada» — «TERMO E CERTIDÃO».

**Os testes:** `tests/test_fluxo_notas.py` (as telas, ponta a ponta) e
`tests/test_requisitos_notas.py` (a matriz legal de `docs/REQUISITOS_LEGAIS.md`).
Nos testes de tela, o escrevente (USER) faz tudo pelas telas, com login e
CSRF. O selador é o falso (`tests/selador_falso.py`), com TLS de verdade, e a
trava do selo pago está LIGADA (`ligar_o_selador(..., protocolo_pago=False)`).
O protocolo e o pagamento são feitos pelo caixa, sem protocolo injetado. O
aparelho falso devolve o texto do selo com os valores da tabela de 2026
(`tests/custas_reais.json`), como o de verdade.

**Legenda:** ✓ coberto por teste · ✗ sem teste · ⚠ defeito (✱ = consertado no
LT02, com teste; ✱✱ = consertado no LD02, 21/10/2026, com teste; ✱✱✱ =
consertado no LD07, 21/10/2026, com teste; sem ✱ = `xfail(strict=True)`,
descrito abaixo) · — não se aplica.

**Etapas:** **P** protocolo do caixa · **$** pagamento (item quitado no
caixa) ou gratuidade · **A** prática do ato · **T** TERMO adequado (o papel
que vai ao livro, ou o papel do ato de balcão) · **S** selo (gasta a unidade
do item pago) · **N** livro/folha/termo, ou o número/ordem · **C** certidão
adequada e fiel ao termo (e o traslado).

### O inventário, lido no código

- **Tipos de ato de livro** (`notas_schema.TIPOS_ATO`): ESCRITURA, PROCURACAO,
  PROCURACAO_PREVIDENCIARIA, SUBSTABELECIMENTO, REVOGACAO, RENUNCIA,
  TESTAMENTO, TESTAMENTO_CERRADO, ATA, ATA_USUCAPIAO.
- **Séries de livro** (`notas_livro.LIVRO_DO_ATO`): ESCRITURA; PROCURACAO
  (procuração, previdenciária, revogação e renúncia); SUBSTABELECIMENTO;
  TESTAMENTO; TESTAMENTO_CERRADO; ATA (ata e ata de usucapião). A numeração
  do termo é contínua por série (CN-MA art. 792).
- **Naturezas** (as 35 minutas de fábrica de `notas_modelos.MINUTAS`):
  - 25 escrituras: compra e venda urbana e rural, doação, cessão de direitos
    hereditários, hipoteca, alienação fiduciária, confissão de dívida com
    dação, permuta, usufruto, inventário e partilha, sobrepartilha,
    partilha/adjudicação, nomeação de inventariante, divórcio, separação,
    conversão de separação em divórcio, restabelecimento da sociedade
    conjugal, união estável, dissolução de união estável, quitação, distrato,
    pacto antenupcial, emancipação e diretivas antecipadas de vontade;
  - as procurações: pública, em causa própria e previdenciária;
  - substabelecimento, revogação e renúncia de mandato;
  - testamento público e auto de aprovação do testamento cerrado;
  - ata notarial, ata de adjudicação compulsória e ata para usucapião.
- **Registros à margem**: a anotação à margem (`notas_anotacoes`: revogação,
  renúncia e substabelecimento anotam o ato anterior — CN-MA art. 831 — e as
  anotações manuais); o arquivamento obrigatório, selo 13.30
  (`notas_arquivamento`); a inutilização de folhas; os termos de abertura e de
  encerramento do livro.
- **Atos de balcão**:
  - cartão de firma (13.17.1);
  - reconhecimento de firma por semelhança e por autenticidade (13.17.2), em
    documento de veículo (13.17.3) e com conteúdo financeiro (13.17.4);
  - termo de comparecimento (presença), que é registro, sem selo;
  - reconhecimento de sinal público (13.17.2);
  - autenticação de cópia e de documento da internet (13.18 por folha);
  - pública forma (`nt_publica_forma`);
  - comunicação de venda de veículo (13.22, `nt_veiculo_detran`).
- **Certidões e traslado** (`notas_certidao.TIPOS`): inteiro teor e breve
  relato (do ato identificado — o breve relato desde o LD02), positiva e
  negativa (pela busca da parte), 13.12.1 / 13.12.3 / 13.12.4, e a busca 13.13.
  O traslado é `/notas/atos/<id>/traslado`.

### Os atos de livro

Um teste por minuta: `test_o_ato_de_livro_vai_do_protocolo_a_certidao_fiel_ao_termo[<minuta>]`
cobre as sete etapas. `test_cada_minuta_de_fabrica_tem_o_seu_caso_ponta_a_ponta`
garante que minuta nova não fica sem caso.

| Ato (minuta) | P | $ | A | T | S | N | C |
|---|---|---|---|---|---|---|---|
| Compra e venda urbana; doação; cessão de direitos hereditários; hipoteca; alienação fiduciária (faixa 13.1.x pelo valor) | ✓ | ✓ | ✓ | ✓ ⚠✱✱✱ INSS e cadastro fiscal (doação, hipoteca, alienação); negócio de risco (cessão) — LD07 | ✓ | ✓ | ✓ |
| Compra e venda rural; confissão/dação; permuta | ✓ | ✓ | ✓ | ✓ ⚠✱ escolha > 300 letras; ⚠✱✱✱ INSS (as três) e cadastro fiscal (confissão, permuta) — LD07 | ✓ | ✓ | ✓ |
| Usufruto | ✓ | ✓ | ✓ ⚠✱✱ escolha aninhada (LD02) | ✓ ⚠✱✱✱ INSS e cadastro fiscal (LD07) | ✓ | ✓ | ✓ |
| Inventário e partilha; sobrepartilha | ✓ | ✓ | ✓ ⚠✱ tipo da CESDI | ✓ ⚠✱ (sobrepartilha) | ✓ | ✓ | ✓ |
| Partilha/adjudicação | ✓ | ✓ | ✓ ⚠✱✱ duas escolhas «ATO» (LD02) | ✓ | ✓ | ✓ | ✓ |
| Divórcio; separação; conversão; restabelecimento; nomeação de inventariante | ✓ | ✓ ⚠✱✱ 13.7 oferecido sem bens (LD02; o restabelecimento e a nomeação não o têm) | ✓ ⚠✱ tipo da CESDI | ✓ ⚠✱ escolha > 300 letras (menos a nomeação) | ✓ | ✓ | ✓ |
| União estável; dissolução; quitação; distrato; pacto antenupcial; emancipação (13.2) | ✓ | ✓ ⚠✱✱ 13.7 na dissolução sem bens (LD02) | ✓ | ✓ ⚠✱ (união, distrato, pacto); ⚠✱✱✱ naturalidade na emancipação (LD07) | ✓ | ✓ | ✓ |
| Diretivas antecipadas de vontade | ✓ | ✓ | ✓ ⚠✱✱ «SE» aninhada (LD02) | ✓ (a trava recusa a marcação antiga no ajuste da casa) | ✓ | ✓ | ✓ |
| Procuração pública; em causa própria (13.9.3 + 13.30) | ✓ | ✓ | ✓ | ✓ ⚠✱✱✱ prévio recolhimento do ITBI na causa própria (LD07) | ✓ ato + arquivamento | ✓ | ✓ |
| Procuração previdenciária, paga | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Procuração previdenciária, ISENTA (INSS) | ✓ | ✓ gratuidade + PDF (⚠✱ a trava não lia a isenção das Notas) | ✓ | ✓ «Selo Isento» | ✓ | ✓ | ✓ |
| Substabelecimento | ✓ | ✓ ⚠✱✱ 13.9.5 oferecido (LD02) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Revogação de mandato | ✓ | ✓ ⚠✱✱ 13.9.6 oferecido (LD02) | ✓ | ✓ | ✓ | ✓ | ✓ e ✓ anota a procuração revogada |
| Renúncia de mandato | ✓ | ✓ ⚠✱✱ 13.9.6 oferecido (LD02) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Testamento público (13.10.1, duas testemunhas) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ com o sigilo (art. 851, § 4º) |
| Testamento cerrado — auto de aprovação (13.10.3) | ✓ | ✓ | ✓ | ✓ ⚠✱✱ «últimas palavras» não são mais cláusula opcional (LD02) | ✓ | ✓ | ✓ |
| Ata notarial; ata de adjudicação compulsória (13.14.1) | ✓ | ✓ | ✓ | ✓ ⚠✱✱✱ ônus e valor venal na adjudicação (LD07); ✓ «não tem valor de título de propriedade» no lugar do «título hábil» (CNN art. 440-G, § 2º — resposta 12 a, LH13) | ✓ | ✓ | ✓ |
| Ata para usucapião (faixa 13.1.x pelo valor venal — CNN art. 423, I) | ✓ | ✓ | ✓ | ✓ ⚠✱✱✱ valor, titular, aquisição da posse, circunscrições, alerta da falsidade, endereço eletrônico (LD07) | ✓ ⚠✱✱ o valor do imóvel na ficha (LD02) | ✓ | ✓ |
| Anotação à margem (revogação → procuração) | — | — (sem ônus, art. 831) | ✓ | — | — sem selo | — | ✓ certidão e traslado com a margem |
| Depósito prévio pagando o item | ✗ | ✗ | — | — | — | — | — |
| Comunicação à serventia de origem (substabelecimento de procuração de fora) | ✗ | — | ✗ | — | — | — | — |

### As certidões

| Certidão | P | $ | Emissão | Adequada | Teste |
|---|---|---|---|---|---|
| Inteiro teor | ✓ | ✓ 13.12.1 do protocolo | ✓ | ✓ ⚠✱ (faltavam o termo nº e o selo do ato com os emolumentos; «lavrada» no masculino) | todos os atos de livro acima |
| Positiva (busca) | ✓ | ✓ | ✓ | ✓ ⚠✱✱ data do ato como data de papel (LD02); ⚠✱✱✱ o termo (ou a ordem) de cada ato (LD07) | `test_a_certidao_pela_busca_e_positiva_com_o_ato_e_negativa_sem_ele`, `test_a_certidao_positiva_escreve_a_data_do_ato_como_data_de_papel`, `test_a_certidao_positiva_diz_o_termo_de_cada_ato_achado` |
| Negativa (busca) | ✓ | ✓ | ✓ | ✓ | idem |
| Breve relato do ato | ✓ | ✓ 13.12.1 do protocolo | ✓ ⚠✱✱ (LD02) | ✓ livro, folha, termo, data, partes, selo e margem | `test_a_certidao_em_breve_relato_traz_os_elementos_do_termo` |
| Traslado | — | — | ✓ | ✓ reproduz o teor, o selo e a margem | todos os atos de livro acima; o da revogação |

### Os atos de balcão

Não há certidão destes atos no sistema. O art. 851 do CN-MA não a exige:
certidão é cópia de escrito em livro ou arquivo, e o papel do ato É o ato.

| Ato | P | $ | A | Papel (T) | S | N | Teste |
|---|---|---|---|---|---|---|---|
| Cartão de firma | ✓ | ✓ 13.17.1 | ✓ | ✓ ficha .odt (⚠✱✱ data de emissão do RG — LD02; ⚠✱✱✱ data de abertura, título eleitoral e a firma três vezes — LD07; ✓ «Preenchimento conferido por: NOME — função», com a linha da assinatura e do carimbo do escrevente que abriu o cartão — resposta 9 b, LH13) | ✓ | ✓ nº da ficha (id) | `test_o_cartao_de_firma_abre_pago_selado_e_a_ficha_traz_o_que_o_art_864_pede`, `test_a_ficha_traz_a_abertura_o_titulo_eleitoral_e_a_firma_tres_vezes`, `test_a_ficha_do_cartao_traz_quem_verificou_o_preenchimento` |
| Reconhecimento por semelhança e por autenticidade | ✓ | ✓ 13.17.2 | ✓ | ✓ etiqueta | ✓ | — | `test_o_reconhecimento_de_firma_sela_pago_e_a_etiqueta_diz_a_especie` |
| Termo de comparecimento (autenticidade) | — | — (sem emolumento, art. 866, § 2º) | ✓ | ✓ ⚠✱✱ a ordem e o selo de cada firma (LD02) | — | ✓ ordem | `test_o_termo_de_comparecimento_da_autenticidade_traz_nome_documento_selo_e_data` e dois xfail |
| Reconhecimento em documento de veículo | ✓ | ✓ 13.17.3 | ✓ | ✓ | ✓ | — | `test_o_reconhecimento_no_documento_de_veiculo_e_por_autenticidade_e_cobra_o_13_17_3` |
| Reconhecimento de várias firmas | ✓ | ✓ | ✓ | ✓ ⚠✱✱ uma tira por firma, com o selo dela (LD02) | ✓ | — | `test_cada_firma_reconhecida_leva_o_seu_selo_na_etiqueta` |
| Reconhecimento de sinal público | ✓ | ✓ 13.17.2 | ✓ | ✓ ⚠✱✱ etiqueta com o selo (LD02) | ✓ | — | `test_o_reconhecimento_de_sinal_publico_sela_pago_pelo_item_da_firma` e xfail |
| Autenticação de cópia, 1 e 2 folhas | ✓ | ✓ 13.18 por folha | ✓ | ✓ ⚠✱✱ uma tira por folha, com o selo dela (LD02); ⚠✱✱✱ a ressalva da rasura do original (LD07) | ✓ um por folha | — | `test_a_autenticacao_de_uma_folha_sela_pago_e_a_etiqueta_e_adequada`, `test_a_autenticacao_de_duas_folhas_sela_e_cobra_uma_vez_por_folha`, `test_a_autenticacao_ressalva_a_rasura_do_original` |
| Autenticação de documento da internet | ✓ | ✓ | ✓ | ✓ ⚠✱✱ endereço, data e hora da conferência (LD02) | ✓ | — | `test_a_autenticacao_da_internet_diz_o_endereco_a_data_e_a_hora_da_conferencia` |
| Pública forma | ✓ | ✓ | ✓ | ✓ ⚠✱✱ papel .odt/PDF com serventia, data, quem expede e selo (LD02) | ✓ | ✓ n./ano | `test_a_publica_forma_numera_sela_pago_e_congela_o_teor` e xfail |
| Comunicação de venda de veículo | ✓ | ✓ 13.22 | ✓ | — (vai ao DETRAN) | ✓ | — | `test_a_comunicacao_de_venda_de_veiculo_sela_pago_antes_de_comunicar` |

### Os defeitos

**Consertados no LT02**, cada um com teste e com mutante que o derruba:

1. **A certidão de inteiro teor não batia com o termo.** Saía sem o número
   do termo e sem o selo do ato e os emolumentos dele. O teor que ela
   reproduz diz «Emolumentos e selo de fiscalização ao final do ato». Saía
   também «substabelecimento lavrada» e «testamento público lavrada».
   - Onde: `modelos_padrao/notas/NOTAS_CERTIDAO_INTEIRO_TEOR.txt` e
     `notas_certidao.selos_do_ato`.
   - A mudança está declarada no ouro do LF06A
     (`MUDOU_DEPOIS_DO_OURO`, `tests/test_modelos_da_casa.py`).
2. **A trava do selo pago não lia a isenção das Notas.** O envelope das
   Notas leva `isento: {value, motivo}`, e só `isento: true` era lido. A
   procuração do INSS isenta e a certidão gratuita ficavam presas esperando
   pagamento. Onde: `ato_selado.selo_e_gratuito`.
3. **Escolha de mais de 300 letras ia crua ao livro.** Em 11 das 35 minutas,
   ela não virava campo da tela nem pendência da trava.
   - Onde: `ri_modelos_atos._ESCOLHA`, cujo limite passou a 1500, como o da
     cláusula.
   - Medido: os modelos do RI e os demais 518 papéis saem iguais.
4. **Marca aninhada que o leitor não alcança agora trava a lavratura.** A
   cláusula «SE» aninhada das diretivas antecipadas ia ao livro.
   - Onde: `notas_teor.marcas_de_modelo_sobrando` e
     `notas_web._pendencias_do_teor`.
5. **A escritura da CESDI nascia sem o tipo da CESDI.** O divórcio, a
   separação, a conversão, o restabelecimento, o inventário, a sobrepartilha
   e a nomeação de inventariante abertos pela minuta travavam por «sem
   natureza da CENSEC». É o mesmo conserto do LG04 para o tipo do RCTO.
   Onde: `notas_web.notas_ato_novo`.

**Consertados no LD02** (21/10/2026, «corrija tudo» — o oficial), cada um com
o teste que era `xfail` e agora passa:

1. **As três minutas que a tela não preenchia.** O usufruto (a `{DURAÇÃO}`
   dentro da `{ATO}`, e uma segunda `{ATO}` com outras opções), a
   partilha/adjudicação (duas `{ATO}` diferentes num campo só) e as diretivas
   (a «SE HOUVER SUBSTITUTO» dentro da «SE NOMEAR PROCURADOR DE SAÚDE»).
   - Onde: `modelos_padrao/notas/minutas/` (as trocas declaradas no ouro do
     LF06D, `MINUTAS_MUDADAS_NO_LD02`). A trava continua valendo para a casa
     que personalizou a minuta antiga.
2. **Testamento cerrado:** as últimas palavras do testador iam entre «», que a
   marcação lê como cláusula opcional; agora entre aspas curvas (CC art. 1.869).
3. **Ata para usucapião:** o valor do imóvel se informa na ficha
   (`/notas/escrituras/<id>/valor` aceita a ata), e o item é a faixa do 13.1
   pelo valor (CNN art. 423, I), conferido no lançamento como na escritura.
4. **Itens próprios da tabela** (13.9.5, 13.9.6, 13.7) oferecidos primeiro na
   tela (`ato_selado.itens_proprios_da_especie`). A escritura com valor zero
   sela pelo caminho sem valor, como a tela mostra.
5. **Certidão em breve relato** (CN-MA art. 851: «cópia integral ou
   resumida»): `notas_certidao`, papel `NOTAS_CERTIDAO_BREVE_RELATO`. Afirma só
   o que o livro registra em campo; não resume o teor.
6. **Certidão positiva:** a data do ato e a da emissão como data de papel.
7. **Balcão:** uma tira por selo (várias firmas, várias folhas); etiqueta do
   sinal público; papel da pública forma; endereço, data e hora da autenticação
   da internet (art. 839, § 1º); ordem do termo de presença, com trava, e o
   selo de cada firma (art. 866); data de emissão do RG na ficha do cartão (art.
   864, § 1º, IV).

**Consertados no LD07** (21/10/2026, «corrija tudo»), 38 dos 40 elementos
que a matriz de `docs/REQUISITOS_LEGAIS.md` dava como faltando; o caminho de
cada um, pelas telas e com o de erro, em `tests/test_notas_ld07_consertos.py`:

1. **As minutas** (24 elementos): o INSS e o cadastro fiscal nas escrituras de
   imóvel (CN-MA art. 800, III e IV), a ciência do negócio de risco na cessão
   (art. 804, § 8º), o ITBI na causa própria (art. 835, III), a naturalidade
   na emancipação (Lei 6.015/1973, art. 90), e o que o CNN pede nas atas de
   usucapião (arts. 401 e 402) e de adjudicação (art. 440-G, I e V). As trocas
   estão declaradas no ouro do LF06D (`MINUTAS_MUDADAS_NO_LD07`).
2. **A qualificação da pessoa física** (CNN art. 111): o documento de
   identidade ou a filiação, a união estável, e o cônjuge e o regime de quem é
   casado.
   - Onde: `nt_ato_partes`, a tela do ato (incluir e completar a parte) e
     `notas_teor.qualificar`, que marca o que falta.
   - A trava da lavratura (o campo em branco) não deixa o ato ir ao livro, nem
     gastar o item pago, com a qualificação incompleta:
     `test_o_ato_com_a_qualificacao_incompleta_nao_vai_ao_livro_nem_gasta_o_item`.
3. **Balcão:**
   - a ressalva do original na autenticação (art. 836);
   - na ficha do cartão, a data de abertura, o título eleitoral e cada forma
     de assinar três vezes (art. 864, § 1º, I, III e V; art. 867);
   - o termo de cada ato na certidão positiva (arts. 792 e 851, § 1º).
4. **O que já estava no papel e a matriz não media:**
   - a ordem do termo de presença;
   - a conferência da autenticação da internet, que agora diz «às … horas»;
   - a moldura da pública forma, que saiu da rota para
     `nt_publica_forma.papel_html` com os mesmos bytes do `.odt`.

**Respondidos pelo oficial em 21/10/2026 (LH13)** — eram os dois `xfail` abertos:

- **Ficha do cartão: quem verificou o preenchimento** (CN-MA art. 864, § 1º,
  VI) — **9 b**. Ao pé da ficha, «Preenchimento conferido por: NOME — função»,
  com a linha da assinatura e do carimbo, do escrevente que ABRIU o cartão:
  nome e função gravados no cartão na abertura (`nt_cartoes.conferente_nome`,
  `conferente_funcao`), e não lidos de quem imprime. O cliente continua
  assinando só os autógrafos e o fecho dele; o delegatário continua fora (a
  decisão de 31/08/2026 mudou só nisso — `test_o_cliente_assina_os_autografos_e_o_preposto_so_a_conferencia`,
  que se chamava `test_so_o_cliente_assina_a_ficha`). Cartão aberto antes
  (e o do E-Ofício) sai com o claro para a caneta. O padrão
  `NOTAS_CARTAO_FICHA` mudou; o modelo PERSONALIZADO da casa no banco não foi
  tocado e não tem a linha até alguém ajustá-lo na tela de Modelos.
- **Ata de adjudicação compulsória** — **12 a**. A minuta `NT-ATA-ADJUDICACAO`
  segue o CNN art. 440-G, § 2º: «a presente ata não tem valor de título de
  propriedade; presta-se à instrução do pedido de adjudicação compulsória
  perante o Registro de Imóveis e poderá ser aproveitada em processo
  judicial», no lugar da frase do CN-MA art. 848, § 2º («título hábil»), que
  saiu (`test_a_ata_de_adjudicacao_nao_se_diz_mais_titulo_habil_para_o_registro`;
  o ouro das minutas declara a troca em `MINUTAS_MUDADAS_NO_LH13`). A minuta
  que a casa já editou em `nt_modelos` não muda.

**Sem teste novo:**
- o depósito prévio pagando o item do selo;
- a comunicação à serventia de origem;
- a remessa à CENSEC e a DOI (fora do caminho protocolo → certidão);
- a inutilização de folhas.

## Registro de Imóveis — LT03 (20/10/2026)

O pedido do oficial: «quero que seja possível do protocolo à certidão (…) TODOS
os atos precisam ter uma certidão adequada» e «TERMO E CERTIDÃO». Esta seção diz,
para cada ato do RI, o que está provado **pelas telas** (cliente de teste do
Flask, login, CSRF, selador falso com TLS e com a etiqueta no formato do
aparelho real) em `tests/test_fluxo_ri.py`, e o que os modelos da casa têm do
que a lei exige em `tests/test_requisitos_ri.py` (matriz em
`docs/REQUISITOS_LEGAIS.md`).

**Legenda:** ✓ coberto por teste · ✗ sem teste (ou não existe no sistema) ·
⚠ defeito (teste `xfail(strict=True)` com o motivo; ver «Defeitos» abaixo) ·
— não se aplica.

**As etapas:** (1) protocolo geral no caixa → (2) pagamento, depósito prévio
ou gratuidade com o PDF → (3) prática do ato → (4) TERMO no livro → (5) selo →
(6) livro, folha e número → (7) certidão fiel ao termo.

### O inventário, lido do código

- **Livros** (LRP art. 173; CN-MA art. 424): 1 — Protocolo (`ri_protocolos`,
  livro `1A`); 2 — Registro Geral (`ri_matriculas` + `ri_atos` R/AV; 4.015 em
  diante é o sistema, abaixo é acervo); 3 — Registro Auxiliar (`ra_registros`,
  `ra_atos`); 4 e 5 — Indicadores Real e Pessoal (busca em `ri_matriculas` e
  `ri_partes`; lançamentos formais só de cancelamento em
  `ri_indicador_lancamentos`). Não há livro de transcrições nem o de aquisição
  por estrangeiro (`livros_obrigatorios`: FALTA).
- **Atos do Livro 2:** abertura de matrícula (`/registro-imoveis/nova` +
  «Selar a abertura», item 16.2); registro R e averbação AV
  (`/registro-imoveis/<id>/atos`, numeração contínua R/AV); os 25 modelos de
  `ri_modelos_atos` — R: compra e venda, doação, permuta, hipoteca, alienação
  fiduciária, usufruto, título de domínio, usucapião, arrematação,
  adjudicação, partilha, integralização; AV: construção, georreferenciamento,
  indisponibilidade, penhora, cancelamento de garantia, estado civil,
  cláusulas, unificação, reserva legal, extinção de usufruto, cancelamento,
  encerramento, alteração de logradouro; encerramento (pelo formulário, com
  `encerra=1`, e o direto); cancelamento de ato («Cancelar este ato»);
  arquivamento por folha (16.39); expurgo de ato de teste.
- **Naturezas:** as 128 da tabela SAUIN (`ri_naturezas.NATUREZAS`, 55 R e 73
  AV) e as 11 do Livro 3 (`ra_registro.NATUREZAS`).
- **Livro 3:** registro (`/livro3/novo`), averbação e cancelamento
  (`/livro3/<id>/lancar`).
- **Certidões:** da matrícula — inteiro teor (por texto e por digitalização),
  ônus e ações reipersecutórias (positiva ou negativa), propriedade, dominial,
  vintenária (`ri_schema.TIPOS_CERTIDAO`); negativa de imóvel pelos
  Indicadores Pessoal e Real; inteiro teor do Livro 3. **Não existem:**
  certidão de transcrição e certidão de prenotação (só o comprovante).
- **Outros papéis:** comprovante de prenotação (`RI_PRENOTACAO`), nota
  devolutiva (`RI_NOTA`) com reingresso, ficha da matrícula (`RI_FICHA`), ficha
  do Livro 3 (`RI_LIVRO3_FICHA`).

### Ato × etapa

| Ato | (1) protocolo | (2) pagamento | (3) prática | (4) termo | (5) selo | (6) livro/nº | (7) certidão |
|---|---|---|---|---|---|---|---|
| Prenotação (Livro 1-A) | ✓ a | ✓ a (caixa); ✓ k (REURB-S isenta) | ✓ a | ✓ a (lista do Livro 1 e comprovante); ✗ sem encerramento diário (LRP art. 184) | ✓ a (PRENOT) | ✓ a (nº de ordem, 1-A) | ✗ não existe certidão de prenotação; o comprovante ✓ a |
| Abertura de matrícula (Livro 2) | ✓ b | ✓ b (caixa); ✓ q (depósito prévio) | ✓ b | ✓ b — consertado: confrontações, qualificação do dono, inscrição municipal, CIB | ✓ b (MATRIC, 16.2) | ✓ b (4.100, CNM, ficha 1/1v) | ✓ d — consertado: a abertura da ficha estruturada |
| R — os 12 modelos de registro | ✓ e | ✓ e; ✓ q (depósito) | ✓ e | ✓ e, c | ✓ e (REGAVD, 16.3.x) | ✓ e (R-01/4100) | ✓ e, d — consertado: o fecho do ato |
| AV — os 13 modelos de averbação | ✓ e | ✓ e | ✓ e | ✓ e | ✓ e (AVESVD, 16.22.2) | ✓ e (AV-01/4100) | ✓ e |
| AV gratuita (REURB-S) | ✓ k | ✓ k (isenta; PDF do comprovante no selo) | ✓ k | ✓ k (marca «isento») | ✓ k (Selo Isento) | ✓ k | ✓ e (mesmo caminho) |
| Arquivamento 16.39 | ✓ l | ✓ l | ✓ l | ✓ l (carimbo com as folhas) | ✓ l (ARQUIV) | ✓ l | ✓ d (o carimbo vai com o ato) |
| Encerramento da matrícula | ✓ m | ✓ m | ✓ m (oficial) | ✓ m | ✓ m | ✓ m (AV-02) | ✓ m (a certidão diz o encerramento e o destino) |
| Cancelamento de ato («Cancelar este ato») | ✓ n | ✓ n, o4 (o item sai do protocolo do título; com dois, a tela pergunta) | ✓ n (oficial) | ✓ n | ✓ o — consertado no LD03: nasce selada; ✓ o2 (o selo que não sai desfaz o cancelamento inteiro); ✓ o3 (clique duplo: uma averbação, um selo, uma unidade) | ✓ n (AV-03) | ✓ n (ônus volta a negativa) |
| Registro no Livro 3 (pacto antenupcial) | ✓ p | ✓ p | ✓ p | ✓ p — consertado: natureza pelo nome, datas, etiqueta do selo; ✓ r (cada ato fecha com quem o praticou — LH13) | ✓ p | ✓ p (registro nº, CNM livro 3) | ✓ p (certidão do Livro 3) |
| Averbação/cancelamento no Livro 3 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Nota devolutiva + reingresso | ✓ s | — | ✓ s | ✓ s (RI_NOTA) | — | ✓ s (nota nº 1; o mesmo nº de ordem no reingresso) | — |
| Lavrar pela tela «Preencher o modelo» | ✓ t, t2 | ✓ t, t2 | ✓ t, t2 — consertado no LD03: a tela leva a prenotação, o protocolo geral, os itens, as partes e o valor; o texto vira minuta, e a recusa volta para ela (t3) | ✓ t2 | ✓ t, t2 | ✓ t2 (R-01) | — |
| Lavrar com `[CAMPO]` do modelo em branco | ✓ u | ✓ u | ✓ u — consertado no LD03: a lavratura recusa (o colchete que não é do modelo lavra — u2; a parte fixa — u3) | ✓ u | ✓ u | ✓ u | — |
| Prenotação vencida, suspensão de prazo | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

### Certidões × etapa (cada uma é ato próprio, com protocolo, pagamento e selo)

| Certidão | (1) protocolo | (2) pagamento | emissão | (5) selo | (6) nº/ano | conteúdo adequado e fiel ao termo |
|---|---|---|---|---|---|---|
| Inteiro teor (texto) | ✓ d | ✓ d (16.24.4 + 16.24.4.1) | ✓ d | ✓ d (CERINT, um por item) | ✓ d | ✓ d, e — a abertura, cada ato com teor, fecho e selo, «Era o que nela continha», os prenotados em aberto, validade, quem expediu |
| Inteiro teor (digitalização) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ (teste próprio em falha conhecida: `test_ri_certidao_digitalizacao`) |
| Ônus — negativa | ✓ f | ✓ f | ✓ f | ✓ f | ✓ f | ✓ f — «NADA CONSTA», «LIVRE E DESEMBARAÇADO», ações |
| Ônus — positiva | ✓ g | ✓ g | ✓ g | ✓ g | ✓ g | ✓ g — a hipoteca como no termo (rótulo, natureza, data, valor, credor) |
| Propriedade | ✓ h | ✓ h (16.24.1) | ✓ h | ✓ h | ✓ h | ✓ h — consertado no LD03: depois da venda afirma a compradora (h2: o quadro de titulares; h3: a venda suspensa pelo selo não mexe nele) |
| Dominial | ✓ i | ✓ i | ✓ i | ✓ i | ✓ i | ✓ i |
| Vintenária | ✓ i | ✓ i | ✓ i | ✓ i | ✓ i | ✓ i |
| Negativa — pessoa (Indicador Pessoal) | ✓ j | ✓ j (+ busca 16.25.7) | ✓ j | ✓ j (certidão e busca) | ✓ j | ✓ j |
| Negativa — imóvel (Indicador Real) | ✓ j | ✓ j | ✓ j | ✓ j | ✓ j | ✓ j — consertado: a ressalva do CN-MA art. 554 |
| Livro 3 — inteiro teor | ✓ p | ✓ p | ✓ p | ✓ p | ✓ p | ✓ p |
| Transcrição | ✗ não existe | | | | | |
| Toda certidão do RI — validade | | | | | | ✓ v (cita o art. 553 — LH13) |

**Os testes** (em `tests/test_fluxo_ri.py`, salvo indicação):
a `test_a_prenotacao_paga_sai_com_selo_e_o_comprovante_traz_o_que_o_livro_1_exige` ·
b `test_a_abertura_da_matricula_sela_e_o_termo_traz_os_requisitos_do_art_176` ·
c `test_o_registro_de_compra_e_venda_sela_e_o_termo_traz_o_art_176_III` ·
d `test_a_certidao_de_inteiro_teor_reproduz_o_termo_da_matricula` ·
e `test_cada_modelo_de_ato_da_casa_lavra_sela_e_sai_igual_no_termo_e_na_certidao[<código>]` (25) ·
f `test_a_certidao_de_onus_negativa_diz_livre_e_desembaracado` ·
g `test_a_certidao_de_onus_positiva_transcreve_a_hipoteca_igual_ao_termo` ·
h `test_a_certidao_de_propriedade_identifica_a_matricula_e_o_imovel` e `test_a_certidao_de_propriedade_depois_da_venda_afirma_o_comprador` ·
h2 `test_a_venda_lavrada_troca_o_titular_no_quadro_e_avisa_quem_saiu` ·
h3 `test_a_venda_que_o_selo_recusou_nao_fica_no_livro_e_o_vendedor_continua_dono` ·
i `test_a_cadeia_dominial_e_a_vintenaria_trazem_a_compra_e_venda_do_termo[DOMINIAL|VINTENARIA]` ·
j `test_a_certidao_negativa_diz_o_que_se_buscou_e_que_nada_consta[PESSOA|IMOVEL]` ·
k `test_a_averbacao_gratuita_sela_isenta_e_o_pdf_da_gratuidade_fica_no_selo` ·
l `test_o_arquivamento_por_folha_sai_com_selo_proprio_e_encerra_a_prenotacao` ·
m `test_o_encerramento_da_matricula_e_do_oficial_sela_e_a_certidao_o_informa` ·
n `test_o_cancelamento_da_hipoteca_e_averbado_selado_e_a_certidao_volta_a_ser_negativa` ·
o `test_a_averbacao_de_cancelamento_ja_nasce_selada` ·
o2 `test_o_cancelamento_cujo_selo_nao_sai_nao_fica_de_pe_e_o_ato_continua_valendo` ·
o3 `test_dois_cliques_em_cancelar_lavram_uma_averbacao_so` ·
o4 `test_o_cancelamento_pergunta_o_item_quando_o_protocolo_tem_mais_de_um` ·
p `test_o_registro_do_livro_3_sela_e_a_certidao_reproduz_o_registro` ·
q `test_o_deposito_previo_do_titulo_paga_a_abertura_e_o_registro_no_selo` ·
r `test_cada_ato_do_livro_3_fecha_com_quem_o_lavrou_e_o_cadastro_mudado_nao_o_troca` ·
s `test_a_nota_devolutiva_formula_as_exigencias_de_uma_so_vez_e_o_titulo_reingressa` ·
t `test_o_modelo_preenchido_na_tela_do_modelo_chega_ao_livro` ·
t2 `test_a_tela_do_modelo_lavra_o_registro_com_as_partes_e_a_compradora_vira_titular` ·
t3 `test_a_recusa_da_lavratura_pela_tela_do_modelo_volta_para_a_minuta_com_o_texto` e `test_a_tela_do_modelo_nao_manda_ao_livro_campo_do_modelo_em_branco` ·
u `test_a_lavratura_recusa_o_campo_do_modelo_que_ficou_por_preencher` ·
u2 `test_o_colchete_que_nao_e_do_modelo_continua_indo_ao_livro` ·
u3 `test_todo_colchete_que_a_parte_fixa_escreve_a_lavratura_reconhece` ·
v `tests/test_requisitos_ri.py::…[…:a validade com o artigo vigente]` e `test_a_validade_das_certidoes_do_ri_cita_o_art_553_em_todo_padrao`.

### Defeitos

**Consertados neste lote (com teste):**
1. **A matrícula nova não tinha onde receber as confrontações nem a
   qualificação do proprietário** (LRP art. 176, § 1º, II, 3 e 4; CN-MA art.
   479, I): a ficha as imprimia, a tela não as pedia. A tela «Nova matrícula»
   ganhou os dois campos e a inscrição municipal; «Cadastrar o proprietário da
   abertura» ganhou a qualificação (a rota já a gravava).
2. **A ficha não imprimia a designação cadastral (inscrição municipal) nem o
   CIB** (LRP art. 176, § 1º, II, 3) — `RI_FICHA`.
3. **A certidão de inteiro teor da ficha estruturada saía sem a abertura**, e
   **nenhuma certidão de inteiro teor trazia o fecho dos atos** (lugar, data,
   «Dou fé», quem praticou) — LRP art. 19, § 11 («a reprodução de todo seu
   conteúdo») — `RI_CERTIDAO_INTEIRO_TEOR`.
4. **A negativa pelo Indicador Real não trazia a ressalva da descrição
   diversa** (CN-MA art. 554) — `RI_CERTIDAO_NEGATIVA_IMOVEL`.
5. **A ficha do Livro 3 imprimia a chave da natureza** («PACTO_ANTENUPCIAL»)
   **e as datas em ISO** («2026-10-20T20:37:36»), **e o carimbo do selo saía
   sem os valores** — `ra_ficha_odt._textos_selo` procurava a etiqueta num
   arquivo fixo da pasta padrão da instalação (`C:\ProgramData\CartorioGestao`
   ou `CARTORIO_GESTAO_DATA`), e não no banco de quem pedia o papel.

O ouro do LF06A foi regravado só nas três chaves dos modelos acima, e o teste
`test_requisitos_ri.py::test_o_ouro_do_lf06a_mudou_so_no_que_o_lt03_acrescentou`
desfaz cada acréscimo e confere que sobra o texto de antes, byte a byte.

**Consertados no LD03 (21/10/2026, «corrija tudo»), com teste:**
- **✓ h — titular atual depois da venda** (LRP art. 19, § 9º). A lavratura
  tinha a sua régua (`papel.startswith("propriet")`) e a correção de parte
  outra (`ri_correcoes.PAPEL_DE_TITULAR`, que conta o adquirente e o
  nu-proprietário). Agora é uma só, e quem transmite sai do quadro de
  titulares — só com o ato de pé (depois do selo; a suspensão não mexe no
  quadro). A linha do vendedor fica, deixa só de ser atual. A venda de parte
  ideal se acerta em «Partes → Corrigir», e a tela avisa.
- **✓ o — cancelamento sem selo** (CN-MA art. 130, § 2º; relato #77).
  «Cancelar este ato» segue o caminho da lavratura comum: recusa antes o que a
  tela sabe (`falta_para_selar`), o item sai do protocolo geral do título
  (com mais de um, a tela pergunta), gasta-se na transação do ato, o selo é
  pedido fora dela, e o selo que não sai **desfaz o cancelamento inteiro** — a
  AV some, o ato volta a valer, o lançamento dos Livros 4 e 5 sai, a
  prenotação se solta e a unidade volta. O alvo se reconfere preso, dentro da
  trava da numeração: dois cliques lavram uma averbação só. As folhas de
  segurança do ato cancelado voltam ao estoque só com o cancelamento de pé.
  O formulário ganhou o item, a natureza e a gratuidade.
- **✓ t — «Enviar para a lavratura» da tela do modelo** leva a prenotação (a
  escolhida; sem escolha, a da matrícula ou a do protocolo que se atende), o
  protocolo geral e os itens (marcados como na ficha), as partes, o valor
  declarado e a qualificação do adquirente (que a parte fixa deixava como
  marcador); e o texto vira minuta antes de ir — a recusa volta para ela, com
  o texto e as partes. Quem lavra continua sendo a rota de sempre.
- **✓ u — `[CAMPO]` do modelo em branco não vai ao livro.** A lavratura
  recusa os campos e as escolhas do modelo informado em `modelo_codigo` e os
  marcadores da parte fixa (`ri_modelos_atos.por_preencher`); o colchete que
  não é do modelo continua lavrando. A tela do modelo não oferece mais
  «Lavrar mesmo assim» para eles.

**Achados e consertados no LD03, ao medir o caminho do erro:**
- **A suspensão do ato com selo recusado falhava no PostgreSQL** sempre que a
  prenotação já estava amarrada ao ato: `ri_protocolos.ato_id` tem chave
  estrangeira para `ri_atos`, o `DELETE` de `ri_minuta.voltar_do_ato`
  estourava («FOREIGN KEY constraint failed») e o ato **ficava de pé sem
  selo**. A prenotação agora se solta antes (h3).
- **O laço das partes da lavratura trocava o tipo do ato pelo do documento**
  (`tipo` era o mesmo nome): com partes, o rótulo da consulta CNIB, a
  auditoria e o recado saíam «CPF-1» no lugar de «R-1».

**Ressalvas da revisão do LD03, consertadas no LD10 (21/10/2026), com teste:**
- **Quem transmitiu sai do quadro só quando se sabe quem é** (h4). Pelo
  documento, quando o ato e o quadro o têm; pelo nome só quando nenhum dos
  dois tem e há um único titular com aquele nome. O homônimo e o documento de
  um lado só não tiram ninguém: vão para o recado («Quadro de titulares a
  conferir») e para a auditoria (`RI_TITULARES_A_CONFERIR`). A leitura e a
  escrita do quadro ficam sob a trava da ficha (`ri_partes.titular:<id>`) e
  com as linhas presas, e a correção de parte prende a dela
  (`test_o_vendedor_sem_cpf_no_ato_fica_no_quadro_e_a_tela_e_a_auditoria_avisam`;
  em `test_ri_correcoes.py`, as regras e as duas corridas).
- **A falha ao tirar o transmitente não vira 500** (h5): o ato fica lavrado e
  selado, o quadro como estava, e a pendência vai ao recado e à auditoria
  (`RI_TITULARES_NAO_ATUALIZADOS`) —
  `test_a_falha_ao_tirar_o_transmitente_nao_derruba_o_ato_ja_lavrado`.
- **O clique duplo em «Enviar» da tela do modelo guarda uma minuta só** (t4):
  a tela leva a marca do envio (`envio`), que entra na `origem_chave`; e a
  minuta se prende antes de se conferir a situação (t5) —
  `test_o_clique_duplo_em_enviar_da_tela_do_modelo_guarda_uma_minuta_so`,
  `test_a_minuta_da_tela_do_modelo_se_guarda_presa_e_dentro_da_trava_da_ficha`,
  `test_a_tela_que_volta_depois_da_lavratura_nao_escreve_na_minuta_lavrada`.
- **O número digitado tem tamanho** (`ri_web.numero_digitado`): protocolo do
  cancelamento e da lavratura, prenotação da tela do modelo, endereços da
  ficha e da prenotação — com 5.000 dígitos, todas caíam na tela de erro —
  `test_o_protocolo_gigante_digitado_nao_derruba_tela_nenhuma_do_ri`.
- **O `abort(redirect(...))` dentro de `db.transaction()` desfaz o que já se
  gravou** (o3b) — `test_o_abort_dentro_da_transacao_desfaz_a_averbacao_ja_gravada`.

**Achado no LD10 ao prender a minuta, e consertado:** a mesma minuta lavrada
em duas abas virava **dois atos** (medido: AV-01 e AV-02 do mesmo texto, com
dois selos), porque a lavratura conferia «a revisar» fora da transação. Agora
ela se reconfere presa, dentro da trava da numeração
(`test_duas_abas_lavrando_a_mesma_minuta_lavram_um_ato_so`); e a «Guardar
revisão» e o descarte também prendem a minuta (`tests/test_ri_minuta_presa.py`).

**Respondidas pelo oficial em 21/10/2026 (LH13)** — eram os dois `xfail` do LD03:
- **14 a — a validade de toda certidão do RI cita o art. 553** do Código de
  Normas da CGJ/TJMA (Prov. COGEX 28/2026), nos padrões `RI_CERTIDAO`,
  `RI_CERTIDAO_NEGATIVA_IMOVEL`, `RI_REPROGRAFICA_VALIDADE` e
  `RI_LIVRO3_CERTIDAO_FECHO`. As certidões do Livro 2 já emitidas reimprimem
  o corpo congelado (`test_a_certidao_emitida_antes_do_lh13_reimprime_o_artigo_que_ela_disse`);
  o fecho da certidão do Livro 3 é montado na impressão, e a segunda via dela
  sai com o 553. Os ouros do LF06A/LF06B declaram a troca, sem regravar.
- **15 a — o ato do Livro 3 grava quem o praticou**: nome, função e artigo de
  quem está logado (`ra_atos.lavrado_*`, pela régua `quem_pratica_o_ato` do
  Livro 2), congelados na lavratura; a ficha fecha cada ato com «Cidade/UF,
  data. Dou fé. A Escrevente Autorizada (NOME).» (CN-MA art. 458). Os atos
  lavrados antes ficam sem fecho
  (`test_cada_ato_do_livro_3_fecha_com_quem_o_lavrou_e_o_cadastro_mudado_nao_o_troca`).

**Vistos no LD03 e deixados para depois (sem teste):**
- O ato que **encerra** a ficha (`encerra=1`) e tem o selo recusado volta a
  ser minuta, mas a ficha **continua encerrada** e os titulares inativos —
  `_marcar_a_ficha_encerrada` entra na transação do ato e a suspensão não o
  desfaz.
- A lista «Protocolo de caixa» da lavratura (`RITEOR.protocolos_do_caixa_abertos`
  e `caixa_ligado_a_prenotacao`) só mostra ABERTO e A_PAGAR: o protocolo já
  PAGO — o estado de quem espera o ato — não aparece para escolher; o balcão
  lavra pelo código digitado com o protocolo em atendimento.

**Sem teste neste lote (✗):** averbação e cancelamento no Livro 3; prenotação
vencida e suspensão de prazo; certidão por digitalização (teste próprio em
falha conhecida); encerramento diário do Livro 1 e certidão de transcrição (não
existem no sistema).
## Registro de Títulos e Documentos e Registro Civil das Pessoas Jurídicas (LT05, 20/10/2026)

> «quero que seja possível do protocolo à certidão. Minha maior preocupação é
> que TODOS os atos precisam ter uma certidão adequada» — e: «TERMO E
> CERTIDÃO» (o oficial, 20/10/2026).

**Como se leu.** O inventário saiu do código, e não de memória: as séries de
`livro_nucleo` (PJ_A, PJ_B, PJ_PROTOCOLO, TD_B, TD_C, TD_F, TD_PROTOCOLO), os
tipos de `rg_registro.TIPOS_ATO` (REGISTRO, AVERBACAO, CANCELAMENTO), as telas
de `rg_web` (título, qualificação, registro, etiqueta, Central), de
`atribuicoes_web` (ficha, averbação, cancelamento, termo em PDF, certidão), de
`rg_notificacao` (notificação, diligência, certidão positiva/negativa,
averbação) e de `rg_livro_contabil` (autenticação, termos, certidão); as
certidões de `atrib_certidao` (texto) e `rg_certidao_pdf` (reprodução); e os
serviços da tabela em `atribuicoes.ATOS` (301–323).

**Como se testa.** `tests/test_fluxo_rtd_rcpj.py` faz o caminho inteiro PELAS
TELAS (login, CSRF), com o selador da bancada de verdade (TLS, porta local) e a
**trava do selo pago ligada**: o selo só sai porque o protocolo foi quitado no
caixa e o escrevente o marcou em atendimento. `tests/test_requisitos_rtd_rcpj.py`
confere, elemento por elemento, o que a lei e as normas mandam o termo e a
certidão dizerem (ver `docs/REQUISITOS_LEGAIS.md`).

Legenda: ✓ coberto por teste · ✗ não existe / sem teste · ⚠ defeito (teste em
`xfail(strict=True)`, ou consertado neste lote — dito na coluna).

### O caminho de cada ato

| Ato | Protocolo | Pagamento / gratuidade | Prática | Termo no livro | Selo | Livro / folha / nº | Certidão fiel ao termo |
|---|---|---|---|---|---|---|---|
| RTD — título recebido no Livro de Protocolo (TD_PROTOCOLO) | ✓ nº de ordem, data, natureza, apresentante | ✓ item do caixa quitado; ✓ gratuidade: selo isento com o fundamento, sem pagamento (LD05, `test_o_registro_gratuito_sela_como_isento_com_o_comprovante`) | ✓ | — | — | ✓ livro e fl. do protocolo | — |
| RTD — qualificação negativa (nota devolutiva) | ✓ | — | ✓ | — | — | — | ✓ nota com exigência, fundamento, prazo, data e assinatura |
| RTD — registro integral, Livro B (TD_B) | ✓ | ✓ só o item do registro (LD05: a diligência e a certidão do mesmo protocolo ficam para os atos delas) | ✓ | ✓ texto do livro e PDF (⚠ consertados: nome da serventia no cabeçalho, data do ato, PDF do registro que não saía, natureza; LD05: assinado por quem lavrou, e não por quem reimprime); ✓ a data e o nº do protocolo e o apresentante, antes do registro, lidos do título (LD09; LRP 136); ⚠ sem livro/folha no alto (LRP 133 — decisão do oficial, `relatorios/LD09.perguntas.md`) | ✓ do aparelho, no razão e no rodapé do termo | ✓ | ✓ inteiro teor (⚠ consertado: volume do livro; LD05: o encerramento, o local, a data, quem subscreveu e o selo de cada ato) |
| RTD — registro por extrato, Livro C (TD_C) | ✓ | ✓ | ✓ | ✓ o extrato — valor, prazo, lugar, partes, testemunhas, firma, imposto — declarado na ficha do título e gravado no ato (LD09; LRP 143; CN-MA 981), com o protocolo e o apresentante | ✓ | ✓ | ✓ |
| RTD — registro facultativo, Livro F (TD_F) | ✓ | ✓ | ✓ | ✓ o total de páginas registradas, pela conta das folhas (LD09; LRP 127-A, § 3º), com o protocolo e o apresentante | ✓ | ✓ | ✓ |
| RTD — averbação | ✓ título de averbação, concluído pelo ato | ✓ item do próprio protocolo | ✓ folha nova | ✓ tipo do ato, data da assinatura, encerramento, selo; ✓ o número de ordem da própria averbação, no alto da folha (LD09; LRP 149 e 153) | ✓ | ✓ | ✓ inteira e só das averbações (⚠ consertado: protocolo da averbação na capa) |
| RTD — cancelamento | ✓ | ✓ | ✓ folha nova, registro CANCELADO, etiqueta recusada | ✓ termo próprio, com a causa e o documento que o autorizou, datado e assinado (LD05, `RTD_TEOR_CANCELAMENTO`; LRP 165; CN-MA 994, § 1º) | ✓ | ✓ | ✓ (⚠ consertado: a certidão calava o ato que cancelou) |
| RTD — notificação extrajudicial positiva | ✓ | ✓ diligência 15.8.1 e certidão 15.8.2 | ✓ diligência no horário e dia da norma | ✓ averbação à margem | ✓ diligência e certidão | ✓ da averbação | ✓ certidão de notificação e certidão do registro com a averbação (⚠ consertado: QR, consulta, emolumentos e quem expediu) |
| RTD — notificação negativa | ✓ | ✓ | ✓ três idas alternadas antes da negativa | ✓ averbação à margem | ✓ | ✓ | ✓ |
| RTD — notificação por carta com AR / por edital (CN-MA 990, 991) | ✗ | ✗ | ✗ não existe (o módulo diz «ficou para depois») | ✗ | ✗ | ✗ | ✗ |
| RTD — título eletrônico pela Central (ONRTDPJ) | ✓ em `test_rg_onrtdpj_web` | — | — | — | — | — | — |
| RCPJ — título no Livro de Protocolo (PJ_PROTOCOLO) | ✓ | ✓ | ✓ | — | — | ✓ | — |
| RCPJ — inscrição de pessoa jurídica, Livro A (PJ_A) | ✓ | ✓ | ✓ | ✓ (mesmos consertos do RTD); ✓ as indicações do art. 120, I a VI, declaradas na ficha do título e gravadas no ato, e a data da apresentação e o apresentante (LD09) | ✓ | ✓ | ✓ inteiro teor (⚠ consertado: saía pelo modelo do RTD) |
| RCPJ — matrícula de periódico, Livro B (PJ_B) | ✓ | ✓ | ✓ | ✓ título do periódico, sede da redação, oficinas, diretor e proprietário (LD09; LRP 123, I) | ✓ | ✓ | ✓ |
| RCPJ — averbação (eleição de diretoria, alteração estatutária) | ✓ | ✓ | ✓ | ✓ (o número de ordem da averbação no alto da folha — LD09) | ✓ | ✓ | ✓ |
| RCPJ — cancelamento / dissolução | ✓ (mesmo código do RTD — teste no RTD) | ✓ | ✓ | ✓ termo próprio (LD05, `RCPJ_TEOR_CANCELAMENTO`; matriz) | ✓ | ✓ | ✓ |
| RCPJ — autenticação de livro contábil | — (pedido próprio) | ✓ item configurado, protocolo pago | ✓ numerada no exercício | ✓ termos de abertura e encerramento congelados | ✓ (⚠ consertado: QR e consulta no papel) | ✓ nº do controle | ✓ certidão da autenticação (⚠ consertado: serventia e CNS) |
| RTD e RCPJ — certidão por texto (.odt) | ✓ protocolo próprio | ✓ 15.10.1 | ✓ numerada, congelada, validade | — | ✓ com QR, consulta e emolumentos | ✓ livro, fl., ato, data | ✓ reproduz o termo: o texto do livro, o encerramento com quem subscreveu, o local e a data, e o selo de cada ato logo abaixo dele (LD05) |
| RTD e RCPJ — certidão por reprodução (PDF) | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ (⚠ consertados: protocolo e apresentação do título, volume, data da emissão e quem expediu) |
| RTD e RCPJ — certidão negativa (serviços 314 e 315) | ✓ protocolo escolhido na tela | ✓ 15.10.1 ligado à certidão antes do selo, e devolvido se o selo não sai | ✓ pesquisa pelo nome e pelo CPF/CNPJ; recusa quem consta (LD05) | — | ✓ nunca sem selo: sem selo, cancelada com o motivo | — | ✓ `RCPJ_RTD_CERTIDAO_NEGATIVA` |
| RCPJ — certidão em breve relato (CN-MA 420, II) | ✓ | ✓ 15.10.1 | ✓ pelos dados da pessoa jurídica gravados na ficha do registro, e só se a leitura é posterior ao último ato (LD05) | — | ✓ | ✓ livro e nº do registro | ✓ `RCPJ_CERTIDAO_BREVE_RELATO` |
| RCPJ — certidão em resumo / informação específica (CN-MA 420, I e III) | ✗ | ✗ | ✗ não existe | — | ✗ | — | ✗ |
| Etiqueta de registro (declaração no título) | — | — | ✓ | — | ✓ selo com QR e valores | ✓ livro, fl., nº, data, protocolo | — |

### Os serviços da tabela (`atribuicoes.ATOS`, 301 a 323) e onde cada um se pratica

| Serviço | Onde se pratica | Teste |
|---|---|---|
| 301 Acima de 3 diligências | notificação, 4ª ida a pedido (15.8.1.1) | ✓ `test_rg_notificacao` (domínio); ✗ pela tela |
| 302 Apostila de Haia | `apostila` (outra funcionalidade) | fora deste lote |
| 303 Averbação de TD com valor declarado | ficha do registro — o selo vai pelo caminho «sem valor» (`ato_selado.CAMINHO_AVERBACAO_TD`) | ✗ (o caminho com valor não existe) |
| 304 Averbação integral de TD sem valor | ficha do registro | ✓ `test_a_averbacao_entra_pelo_protocolo…[rtd-…]` |
| 305 Registro integral de TD com valor | título com `valor_declarado`; item por faixa no caixa | ✗ sem teste |
| 306 Registro integral de TD sem valor | título → Livro B | ✓ `test_o_registro_vai_do_protocolo…[rtd-livro-B…]` |
| 307 Registro resumido de TD com valor | título → Livro C | ✗ sem teste |
| 308 Registro resumido de TD sem valor | título → Livro C | ✓ `[rtd-livro-C…]`; o termo com o extrato: `test_o_termo_declara_o_protocolo…[rtd-livro-C-o-extrato]` (LD09) |
| 309 Registro para atos em geral (RCPJ) | título → Livro A | ✓ `[rcpj-livro-A…]` |
| 310 Autenticação de livros contábeis | `rg_livro_contabil` | ✓ `test_a_autenticacao_de_livro_contabil…` |
| 311, 312 Buscas em livros | item de busca da certidão (`_busca_do_form`) | ✓ `test_selo_de_busca_da_certidao`; ✗ neste fluxo |
| 313 Cancelamento, inclusive busca e certidão | ficha do registro | ✓ `test_o_cancelamento_entra_na_certidao…` |
| 314 Certidão negativa (PJ) | `/atribuicoes/certidoes` → «Certidão negativa» (LD05) | ✓ matriz; pela tela, o do RTD |
| 315 Certidão negativa (TD) | `/atribuicoes/certidoes` → «Certidão negativa» (LD05) | ✓ `test_a_certidao_negativa_do_rtd_sai_pela_tela` e os caminhos de erro |
| 316 Certidão de notificação | `rg_notificacao` | ✓ positiva e negativa |
| 317 Diligência fora da zona urbana | notificação rural (15.8.1.2, por km) | ✓ `test_rg_notificacao` (régua); ✗ pela tela |
| 318 Matrícula de oficina, jornal e periódico | título → Livro B do RCPJ | ✓ `[rcpj-livro-B…]`; o termo com o art. 123: `test_o_termo_declara_o_protocolo…[rcpj-livro-B-o-art-123]` (LD09) |
| 319 Averbação de pessoa jurídica | ficha do registro | ✓ `[rcpj-averbacao…]` |
| 320 Certidão de atos de processo de PJ | não há forma própria (sai a de inteiro teor) | ✗ |
| 321, 322 Certidão por peça reproduzida (PJ, TD) | certidão em PDF (`/atribuicoes/certidoes/<id>/imprimir`) | ✓ passo 9 do teste de registro |
| 323 Inscrição de pessoa jurídica | título → Livro A | ✓ `[rcpj-livro-A…]`; o termo com o art. 120: `test_o_termo_declara_o_protocolo…[rcpj-livro-A-o-art-120]` (LD09) |

O depósito prévio (`caixa_depositos`) cobre o selo pela mesma trava, mas não
foi exercitado neste fluxo (✗): o pagamento aqui é a quitação no caixa.

### Os defeitos

**Consertados neste lote (cada um com teste, e provado por mutação — o teste
cai quando o conserto é desfeito):**

1. O termo em PDF saía com o cabeçalho «— CNS 000000», sem o nome da serventia:
   as três rotas que montam o teor não mandavam `unit_short`
   (`atribuicoes_web.rcpj_rtd_ato_teor`, `rcpj_rtd_teor_averbacao_previa`,
   `rg_web.rcpj_rtd_titulo_teor_previa`).
2. O termo do REGISTRO não saía pela tela: `/rcpj-rtd/ato/<id>/teor` só aceitava
   anexo ligado ao ato, e só a averbação liga. Agora cai no documento do
   registro e, na falta, no do título.
3. O termo era datado do dia da impressão — a segunda via de amanhã diria que o
   ato foi lavrado amanhã. Agora leva a data do ato.
4. O termo do registro saía sem a natureza («Tipo do ato»): a rota só a lia do
   teor digitado. Agora cai na natureza do registro (a do protocolo).
5. A certidão por texto dizia `no Livro "B"`, sem o volume, em todo registro
   lavrado aqui (`volume` é coluna da carga). Agora usa o número do livro.
6. A certidão do registro cancelado dizia «encontra-se CANCELADO» e calava o ato
   que o cancelou (número e razão — LRP art. 165).
7. A certidão do RCPJ saía pelo modelo do RTD (`emitir` perguntava se o painel
   era «RCPJ», e o painel se chama «RCPJ_RTD»): o ajuste da casa no
   RCPJ_CERTIDAO não chegava a papel nenhum.
8. A certidão em PDF dizia «protocolado sob nº —» e punha a data do registro no
   lugar da apresentação; saía sem o volume, com a data e o nome de quem
   reimprime. Agora: protocolo e data do título (ou o item que a averbação
   gastou), volume do livro, data da emissão e quem expediu.
9. A certidão de notificação mostrava só o número do selo: sem QR, sem
   consulta, sem emolumentos e sem quem expediu.
10. A certidão da autenticação de livro não dizia de que serventia era; e o
    papel dos termos e da certidão não trazia QR nem consulta do selo.

**Consertados no LD05 (21/10/2026), cada um com o teste que era xfail e o do
caminho de erro:**

11. O registro pelo título selava TODOS os itens do protocolo — os da diligência
    e da certidão do mesmo atendimento, e os que outro ato já tinha gastado.
    Agora sela os itens marcados na tela do título (que mostra os do protocolo,
    marcados só os do registro — `rg_registro.item_e_do_registro`), sempre pelo
    saldo do caixa (`test_o_registro_pelo_titulo_so_sela_o_item_do_registro`,
    `test_a_ficha_do_titulo_marca_so_os_itens_do_registro`,
    `test_o_item_que_outro_ato_gastou_nao_sela_de_novo_e_o_marcado_vale`).
12. O ato gratuito: o registro pelo título com o fundamento escrito sela
    «isento» (`DadosIsento`: value + motivo), sem pagamento; sem fundamento,
    nada se lavra (`test_o_registro_gratuito_sela_como_isento_com_o_comprovante`,
    `test_o_ato_gratuito_sem_fundamento_nao_se_lavra`).
13. O cancelamento tem termo: a causa e o documento que o autorizou, datado do
    dia do ato e assinado por quem lavrou, com o selo no rodapé
    (`test_o_cancelamento_tem_termo_datado_e_assinado`).
14. O termo é assinado por quem lavrou o ato, e não por quem o reimprime
    (`rg_registro.subscritor_do_ato`).
15. A certidão por texto reproduz o fecho do termo de cada ato — o
    encerramento com quem subscreveu, o local e a data — e o selo de cada ato
    logo abaixo dele (`test_a_certidao_por_texto_reproduz_o_encerramento_e_quem_subscreveu`,
    `test_a_certidao_por_texto_traz_o_selo_de_cada_ato_que_reproduz`).
16. A certidão negativa do RTD e do RCPJ existe: pesquisa pelo nome e pelo
    documento, recusa quem consta, liga o item à certidão antes do selo e o
    devolve se o selo não sai — e a certidão sem selo fica cancelada
    (`test_a_certidao_negativa_do_rtd_sai_pela_tela`,
    `test_a_negativa_nao_sai_para_quem_consta_dos_livros`,
    `test_a_negativa_sem_pagamento_nao_sai_sem_selo_e_o_item_volta`).
17. A certidão do RCPJ em breve relato, pelos dados da pessoa jurídica que quem
    leu o estatuto grava na ficha do registro, e só com leitura posterior ao
    último ato (`test_a_certidao_do_rcpj_em_breve_relato_traz_os_elementos_do_art_420`,
    `test_o_breve_relato_sem_os_dados_da_ficha_ou_com_dados_velhos_nao_sai`).

**Consertados no LD09 (21/10/2026) — o termo declara o que a lei manda
declarar; cada um era `xfail` da matriz (`test_requisitos_rtd_rcpj.py`) e tem
teste pela tela:**

18. O termo do registro diz, antes da trasladação, a data e o número do
    protocolo e o apresentante, lidos do título (LRP art. 136; art. 120, caput
    e VI — `rg_registro.dados_do_termo`); a prévia do título diz o mesmo, e
    deixou de sair sem «Tipo do ato»
    (`test_o_termo_declara_o_protocolo_e_o_que_o_livro_pede_e_a_segunda_via_tambem`,
    e o passo 6 de `test_o_registro_vai_do_protocolo…`).
19. As declarações do livro: o extrato do Livro C (LRP art. 143; CN-MA art.
    981), as indicações do art. 120 na inscrição da pessoa jurídica e as do
    art. 123, I, na matrícula do periódico. Quem lavra as escreve na ficha do
    título (ou na do registro novo); elas vão para o ATO (`rg_atos.declaracoes`)
    na lavratura, e o termo as reimprime iguais em qualquer segunda via — a
    leitura do estatuto gravada depois (a do breve relato) não muda a inscrição.
    A declaração de outro livro é recusada antes do número: nenhum ato, nenhum
    selo, o item do protocolo intacto
    (`test_a_declaracao_de_outro_livro_e_recusada_e_nada_se_lavra`,
    `test_o_registro_novo_tambem_pergunta_as_declaracoes_e_recusa_a_de_outro_livro`).
20. O total de páginas do Livro F, pela conta das folhas que o PDF traslada
    (LRP art. 127-A, § 3º — `test_o_total_de_paginas_sai_no_livro_f_e_so_nele`).
21. O número de ordem da averbação, no alto da folha do termo dela (LRP arts.
    149 e 153); a intro, que vai ao livro, não muda
    (`test_a_averbacao_entra_pelo_protocolo…`,
    `test_o_cabecalho_da_averbacao_diz_o_numero_dela_e_a_previa_nao_inventa`).

**Abertos, com `xfail(strict=True)` e o artigo:**

- Não há certidão do RCPJ em resumo nem informação específica (CN-MA 420, I e
  III).

**Decidido pelo oficial em 21/10/2026 (LH13), pergunta 28:** o termo NÃO diz o
livro e a folha no alto. «28 tem que ser lida em conjunto com outras normas,
inclusive estaduais que permitem que esses livros sejam digitais, nao fazendo
sentido colocar livro e folha» — a LRP art. 133 se lê com as normas do livro
digital, e a ordem de 11/09/2026 fica. Os 7 `xfail` viraram o registro da
decisão: `test_o_papel_traz_o_elemento…[TERMO_*-o livro e a folha FORA do alto
do termo…]` confere que o cabeçalho não os cita, e
`test_a_casa_nao_consegue_por_livro_e_folha_no_alto_do_termo`, que a tela de
Modelos continua recusando o ajuste que os ponha.

## Tabelionato de Protesto (LT04, 20/10/2026)

Pedido do oficial: «do protocolo à certidão» e «TERMO E CERTIDÃO». Esta seção
lista, **lido do código**, cada ato do Protesto e cada etapa da vida dele, e diz
qual teste cobre. Os testes de ponta a ponta estão em
`tests/test_fluxo_protesto.py` (pelas telas: login, CSRF, caixa, protocolo pago,
selador de mentira) e a matriz dos elementos obrigatórios está em
`tests/test_requisitos_protesto.py` (ver `docs/REQUISITOS_LEGAIS.md`).

Legenda: ✓ coberto por teste · ✗ sem teste ou sem caminho no sistema · ⚠
defeito (`xfail(strict=True)` com o artigo, ou consertado no LT04 ou no LD04 —
dito na linha). **F** = `test_fluxo_protesto.py`; **R** = `test_requisitos_protesto.py`;
**AW** = `test_atribuicoes_web.py`; **LG5** = `test_protesto_lg05_web.py`; **E15** =
`test_protesto_aviso_entrega_15_10.py`.

### O que existe (inventário)

- **Título**: as 64 espécies do contrato da CRA (`protesto_cra.ESPECIES`), 10
  usadas pela casa (`protesto.ESPECIES_USADAS_POR_ESTA_CASA`: DMI, CDA, CBI, DSI,
  DM, ATC, NP, CTI, SJ, FPS). A espécie não muda o fluxo: os atos são os mesmos.
  Origem CRA, CENPROT ou MANUAL (balcão, `/protesto/novo`). Tipo comum ou
  falimentar; motivo falta de pagamento, de aceite ou de devolução.
- **Situações** (`protesto.SITUACOES_TITULO`): RECEBIDO → APONTADO → INTIMADO →
  PROTESTADO → CANCELADO; PAGO e DESISTIDO são finais; o pagamento só cabe antes
  do protesto (LH13, 21/10/2026).
- **Atos** (`pt_atos.tipo`): APONTAMENTO; INTIMACAO (pessoal, por edital,
  digital); PROTESTO; PAGAMENTO; DESISTENCIA; CANCELAMENTO (hipóteses PAGAMENTO,
  ANUENCIA_CREDOR, ORDEM_JUDICIAL); SUSTACAO e REVOGACAO_SUSTACAO;
  EFEITO_SUSPENSIVO e REVOGACAO_EFEITO_SUSPENSIVO. RETIRADA, ARQUIVAMENTO e
  CERTIDAO estão em `TIPOS_ATO`, mas não têm função que grave.
- **Séries de livro** (`livro_nucleo`): PT_APONTAMENTO (52 por face), PT_PROTESTO
  (um por face, frente e verso), PT_PAGAMENTO (120 por folha) e PT_PROTOCOLO
  (diária, sem ato que a use). O Livro de Índices (CN-MA art. 896) **falta**
  (`livros_obrigatorios`).
- **Papéis**: aviso de intimação, edital, instrumento de protesto, certidão
  NEGATIVA, POSITIVA e de CANCELAMENTO (`pt_certidoes`), certidão diária em
  forma de relação, Livro de Protocolo e Livro de Pagamentos (vistas montadas
  dos atos), retorno à CRA; desde o LD04, o termo do cancelamento
  (`PT_TERMO_CANCELAMENTO`, em `pt_atos.teor`) e a quitação do título pago
  (`PT_QUITACAO`, `/protesto/pagamentos/<ato>/quitacao.odt`).
- **Caminhos do selo** (`ato_selado.CAMINHO_DO_ATO`): `titulo` (protesto),
  `atos-em-geral` (intimação), `pagamento`, `retirada` (desistência),
  `baixa-cancelamento`, `certidao`. As ordens judiciais não selam, e o
  apontamento também não, desde 21/10/2026 (P-B, ordem do oficial, LH06).

### Ato × etapa

| Ato | Protocolo do caixa | Pagamento / depósito / gratuidade | Prática do ato | TERMO no livro | Selo | Livro / folha / nº | Certidão fiel ao termo |
|---|---|---|---|---|---|---|---|
| Apontamento (balcão) | ✓ F `test_o_apontamento_ocupa_o_livro_de_apontamento_e_nao_pede_selo` | ✓ F (quitar no protocolo); gratuidade ✗ | ✓ F | ✓ linha do Livro de Protocolo (F), com o CPF/CNPJ do devedor — F `test_o_livro_de_protocolo_traz_o_cpf_do_devedor`, R (CN-MA art. 906; consertado no LD04) | não sela desde 21/10/2026 (P-B, ordem do oficial; LH06): sem pedido ao selador e sem anular o ato — F, e `test_o_apontamento_sem_item_nao_pede_selo_e_fica_lancado`. Até então selava por `/selo/protesto/titulo` (LT04) | ✓ F (PT_APONTAMENTO 1/1/1) | ✓ negativa a terceiro (F); ✓ a pedido escrito do devedor (ou por ordem judicial) a certidão traz o que consta do Livro de Protocolo — F `test_o_devedor_tira_certidao_do_apontamento…` (CN-MA art. 906, § 2º; consertado no LD04) |
| Apontamento (CRA, em lote) | não se aplica (a posteriori) | não se aplica | ✓ F `test_o_titulo_da_cra_entra_apontado…` (remessa pela tela) | ✓ (o mesmo livro) | ✗ o lote não sela (CN-MA art. 881, § 1º) | ✓ F | ✓ retorno à CRA com o protocolo (F) |
| Intimação pessoal (aviso entregue) | não se aplica (cobra no desfecho) | não se aplica | ✓ F `test_a_intimacao_chega_igual…[PESSOAL]` | ✓ ocorrência no Livro de Protocolo e frase no termo do protesto (F) | não sela (a intimação vai no selo do desfecho) | não ocupa livro | ✓ aviso (CN-MA arts. 920/923) e instrumento com a mesma data (F, R) |
| Intimação por edital | idem | idem | ✓ F `…[EDITAL]` | ✓ idem | idem | não ocupa livro | ✓ edital (CN-MA art. 922, § 3º) e instrumento (F, R) |
| Intimação pela ficha (`/lancar`) | ✓ F | ✓ F | ✓ F `test_a_intimacao_por_edital_lancada_pela_ficha…` | ✓ | ✓ F (`atos-em-geral`; ⚠ consertado: a de edital selava como pessoal) | não ocupa livro | ✓ (a do aviso) |
| Intimação eletrônica (Resolve, ou a marca da ficha) | — | — | ✓ E15 `test_resolve_confirmada_lavra_a_digital…`; F (pela ficha) | ✓ frase própria no termo («por meio eletrônico») | não sela pelo aviso | — | ✓ termo e instrumento com a mesma certidão da intimação eletrônica (`PT_INSTRUMENTO_INTIMACAO_DIGITAL`) — F `test_a_intimacao_eletronica_sai_igual_no_termo_e_no_instrumento`, R (Lei 9.492 art. 22, IV; CN-MA art. 919, § 1º; consertado no LD04) |
| Protesto | ✓ F `test_o_protesto_lavrado_e_o_instrumento…` | ✓ F; a posteriori ✓ F (CRA) e LG5 | ✓ F | ✓ o registro traz, no alto, a qualificação (lugar e data do registro, protocolo, apresentante, título, credor e devedores com documento e endereço — peça `PT_TERMO_QUALIFICACAO`, com a redação do instrumento) — F `test_o_registro_do_protesto_traz_os_elementos_do_art_22`, R (Lei 9.492 arts. 21, § 4º, e 22; consertado no LD04) | ✓ F (natureza 7; ⚠ consertado: o livro ia como o `id` interno, e as partes vazias) | ✓ F (PT_PROTESTO 1/1/1) | ✓ instrumento e positiva fiéis ao registro, item a item (F, R); ✓ o balcão pede o apresentante, e ele vai ao aviso, ao registro e ao instrumento — F `test_o_titulo_do_balcao_leva_o_apresentante…` (Lei 9.492 art. 22, II; consertado no LD04); ✓ com o CPF/CNPJ (no aviso) e o endereço (no registro e no instrumento), do balcão ou do cadastro dos apresentantes pelo código da CRA — F `test_o_balcao_pede_o_documento_e_o_endereco_do_apresentante…`, R (CN-MA arts. 884, I, e 923; consertado no LD08) |
| Pagamento (antes do protesto) | ✓ F `test_o_pagamento_antes_do_protesto…` | ✓ F | ✓ F | ✓ linha do Livro de Pagamentos, art. 930 (F, R) | ✓ F (natureza 8) | ✓ F (PT_PAGAMENTO 1/1/1) | ✓ negativa a terceiro (CN-MA art. 934); ✓ quitação do título ao devedor, só do pagamento lançado no livro, com o selo dele — F `test_o_pagamento_da_ao_devedor_a_quitacao…`, `test_a_quitacao_so_sai_do_pagamento_que_ficou_lancado` (Lei 9.492 art. 19, § 2º; CN-MA arts. 927 e 930, § 1º; consertado no LD04) |
| Pagamento (depois do protesto) | — | — | ✗ recusado desde 21/10/2026 (LH13, pergunta 17 c: «protesto nao pode ser pago na serventia depois de lavrar»); a ficha não oferece e diz o caminho (credor + carta de anuência + cancelamento, Lei 9.492 art. 26, § 1º; CN-MA art. 942, § 2º) | — | — | — | ✓ o legado PAGO com protesto em pé (regra de 24/08/2026) se cancela pela anuência ou por ordem judicial e sai da certidão — F `test_o_protesto_pago_depois_de_lavrado_ainda_se_cancela` |
| Desistência | ✓ F `test_a_desistencia_sela_a_retirada…` | ✓ F | ✓ F | ✓ ocorrência «retirado pelo apresentante» (F) | ✓ F (`retirada`, natureza 9) | não ocupa livro | ✓ negativa a terceiro (CN-MA art. 934) |
| Sustação e revogação | não se aplica | não se aplica | ✓ F `test_a_sustacao_impede_o_protesto…` | ✓ ocorrências no Livro de Protocolo (F) | não sela (F confere) | — | ✓ positiva depois do protesto sem nova intimação (F) |
| Efeito suspensivo e revogação | não se aplica | não se aplica | ✓ F | ✗ sem averbação lavrada | não sela | — | ✓ CNN art. 263-K (LH13, pergunta 18 a): a ordem leva a marca (provisória/definitiva, manda negativa, segredo de justiça); a provisória sai «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA» com o registro, a ação, o caráter e o fecho; a definitiva e a que manda negativa ficam fora; em segredo, só a sustação e o processo; a ordem sem marca (anterior) fica fora e as telas avisam — F `test_protesto_com_efeitos_suspensos_sai_como_consta_com_sustacao_precaria`, `test_a_decisao_definitiva…`, `test_a_ordem_que_manda_emitir_negativa…`, `test_no_segredo_de_justica…`, `test_a_ordem_sem_marca…`; cobrada e selada como positiva (17.5.1/17.5.2 — a tabela não tem item próprio) |
| Cancelamento | ✓ F `test_o_cancelamento_sela_a_baixa…` | ✓ F | ✓ F | ✓ lavra o termo do cancelamento em `pt_atos.teor` (`PT_TERMO_CANCELAMENTO`: o registro cancelado, a hipótese e o fundamento) — F `test_o_cancelamento_lavra_o_termo_da_baixa` (Lei 9.492 art. 26, § 6º; consertado no LD04) | ✓ F (`baixa-cancelamento`) | não ocupa livro (anotação) | ✓ negativa a terceiro; ✓ certidão de cancelamento a pedido escrito do devedor, com o fecho do art. 26 (F, R) |
| Certidão negativa / positiva / de cancelamento | ✓ F | ✓ F (item 17.5.1 pago); gratuidade ✗ | ✓ F | teor congelado (`pt_certidoes.teor`) | ✓ F (selo próprio, QR e consulta no papel; emolumentos que o selo declara — F `test_os_emolumentos_que_o_selo_declara…`) | numeração por exercício | ✓ F, R; ✓ a linha da positiva traz a data do protocolo e o tipo do endosso — R (CNN art. 259, p. ú., V e VII; consertado no LD08) |
| Certidão em forma de relação | — | — | ✓ LG5 `test_a_relacao_pela_tela…` | — | não sela | numeração por exercício | ✓ com a data do vencimento — F `test_a_relacao_diaria_traz_os_dados_do_art_130_do_cnn`, R (CNN art. 130; consertado no LD04) |
| Selo que não sai | — | — | ✓ F `test_selo_recusado_devolve_o_titulo…`, `test_intimacao_sem_selo…` | — | ⚠ consertado no LT04: o título ficava na situação nova com o ato anulado | — | ⚠ consertado no LT04: a certidão lia o ato anulado (F `test_protesto_que_nao_se_lavrou…`, `test_a_baixa_que_nao_se_lavrou…`) |

### Consertado no LT04

1. **Selo que não sai devolvia o ato, e não o título** (`atribuicoes_web.protesto_lancar`).
   O ato se anulava e o título ficava PROTESTADO, PAGO, DESISTIDO, CANCELADO ou
   INTIMADO por um ato que não existiu. O «tente de novo» era recusado, e a
   intimação anulada deixava protestar sem intimação válida. Agora o título
   volta à situação de antes. Dois testes do AW passavam por isso («Ato NÃO
   lançado» também diz «lançado»); eles foram ajustados para lançar com o item,
   como o balcão faz.
2. **A certidão lia o ato anulado** (`protesto_certidao.buscar`). O protesto
   anulado saía na positiva. A baixa anulada tirava da certidão um protesto em
   pé, e a pessoa saía com NEGATIVA. Agora vale o filtro `cancelado = 0`, o mesmo
   da relação, do XML da CENPROT e do repasse.
3. **O selo do ato declarava o livro errado e nenhuma parte**
   (`_selar_o_protesto`). O livro ia como o `id` interno de `nu_livros`. Agora
   vai o número do livro e o devedor em `parteAto`, como o selo real de
   pagamento de 06/08/2026 (`test_ato_selado`).
4. **A intimação por edital lançada pela ficha selava como pessoal.** Agora o
   modo vai ao envelope.

### Consertado no LD04 (21/10/2026)

O oficial, sobre a lista dos defeitos do LT04: «corrija tudo». Oito dos dez
`xfail` do fluxo saíram; os dois que o próprio motivo dava como «a decidir»
ficaram, com a pergunta em `relatorios/LD04.perguntas.md`.

1. **Livro de Protocolo com o CPF/CNPJ do devedor** (CN-MA art. 906): coluna
   própria (`protesto_livros`, `PT_MOLDURAS`); no fim do livro desde o LD11.
2. **Certidão a pedido escrito do devedor, ou por ordem judicial, com o Livro
   de Protocolo** (CN-MA arts. 905, parágrafo único, e 906, § 2º): o título só
   apontado, pago ou retirado entra num parágrafo próprio, com as ocorrências
   (`protesto_certidao.paragrafo_do_protocolo`, rótulos em `PT_CERTIDAO_LINHA`).
   A negativa continua dizendo que protesto não há.
3. **Intimação eletrônica igual no termo e no instrumento** (CN-MA art. 919,
   § 1º): `protesto_instrumento.dados` lê a marca `digital`, e a peça
   `PT_INSTRUMENTO_INTIMACAO_DIGITAL` certifica.
4. **O registro do protesto com a qualificação do art. 22**: a peça
   `PT_TERMO_QUALIFICACAO` vai no alto do termo, com a redação do instrumento
   (`protesto_instrumento.pedacos_da_descricao`). O texto da casa
   (`PT_TERMO_PROTESTO`) não mudou, e o termo que a casa personalizou também
   recebe a qualificação (art. 21, § 4º).
5. **O apresentante no cadastro do balcão** (`/protesto/novo`; Lei 9.492, art.
   22, II). O endereço dele ficou sem fonte até o LD08 (abaixo).
6. **A quitação do título** (Lei 9.492, art. 19, § 2º; CN-MA art. 927): papel
   `PT_QUITACAO`, montado do pagamento lançado no livro (art. 930, § 1º), com
   o selo do pagamento; o pagamento anulado não tem quitação.
7. **O termo do cancelamento** (Lei 9.492, art. 26, § 6º): papel
   `PT_TERMO_CANCELAMENTO`, gravado no ato.
8. **A relação diária com a data do vencimento** (CNN art. 130).

### Consertado no LD08 (21/10/2026)

Os papéis do Protesto, elemento por elemento: os quatro itens que a matriz
(`tests/test_requisitos_protesto.py`) ainda tinha em `xfail` saíram. Os outros
da lista do LD08 o LD04 já tinha consertado.

1. **O CPF/CNPJ do apresentante no aviso** (CN-MA art. 923; CNN art. 356,
   § 4º): claro `{documento_do_apresentante}` em `PT_AVISO_INTIMACAO`.
2. **O endereço do apresentante no instrumento e no registro** (Lei 9.492,
   art. 22, II; CN-MA art. 914, III): rótulo `apresentante_endereco` em
   `PT_INSTRUMENTO_DESCRICAO` — o pedaço é o mesmo do termo
   (`PT_TERMO_QUALIFICACAO`). O item II da conferência do art. 22 se satisfaz
   quando o endereço existe.
   - **A fonte dos dois** é `protesto.apresentante_do_titulo`: o próprio
     título (o balcão pede o CPF/CNPJ e o endereço, CN-MA art. 884, I, e
     recusa o documento que não fecha o dígito) ou o cadastro dos
     apresentantes, pelo código da CRA (`pt_apresentantes`, que já guardava o
     CNPJ para o XML da CENPROT e ganhou o endereço; tela Protesto → XML da
     CENPROT). A ficha do título mostra o apresentante e o que falta.
3. **O tipo do endosso na certidão positiva** (CNN art. 259, p. ú., V):
   «endosso translativo» ou «endosso mandato», logo depois do apresentante
   (`PT_CERTIDAO_LINHA`: `endosso`, `endosso_M`, `endosso_T`). Sem endosso,
   nada.
4. **A data do protocolo na certidão positiva** (CNN art. 259, p. ú., VII):
   «protocolo N de DD/MM/AAAA», com a data do apontamento
   (`PT_CERTIDAO_LINHA.protocolo_com_data`).

Três perguntas ficaram para o oficial, sem `xfail` (o balcão deve EXIGIR o
documento e o endereço? o título da CRA sem cadastro avisa? o «sem endosso»
se escreve?): `relatorios/LD08.perguntas.md`.

### Consertado no LD11 (21/10/2026)

As ressalvas da revisão do LD04. Cada conserto tem teste que falha sem ele
(provado com mutante, um conserto desfeito por vez).

1. **A busca da pessoa é uma regra só**, na certidão e no Livro de Protocolo
   (`protesto_certidao.onde_casa_o_devedor`):
   - com o CPF/CNPJ, casa pelo documento, e o nome não amplia — era documento
     OU nome, e o homônimo de outro CPF entrava na positiva (a terceiro) e no
     parágrafo do Livro de Protocolo (a pedido escrito; CN-MA art. 906, § 2º)
     — F `test_a_certidao_pedida_com_o_cpf_nao_traz_o_homonimo`;
   - sem documento, pelo nome, que é texto e não curinga: o nome «%» casava
     com todos os devedores (`ILIKE ... ESCAPE '\'`).
2. **A quitação do pagamento sem título** recusa com recado
   (`QuitacaoError`), e não com `TypeError`.
3. **A quitação pede o papel de quem lança o pagamento** (ADMIN, MANAGER,
   USER): o AUDITOR não a emite, e a ficha dele não oferece o botão; a
   auditoria da emissão fica — F
   `test_a_quitacao_pede_o_papel_de_quem_lanca_o_pagamento`.
4. **A coluna nova vai para o fim**: o VENCIMENTO na relação diária e o
   CPF/CNPJ do devedor no Livro de Protocolo. As colunas de antes do LD04
   ficam onde estavam, para quem lê por posição.

### Consertado no LD12 (21/10/2026)

A ressalva da revisão do LD11: com o CPF/CNPJ no pedido, o devedor gravado
SEM documento sumia da certidão, e ela saía NEGATIVA para quem tem protesto.

1. **Com o CPF/CNPJ, casa o documento OU o nome inteiro do devedor sem
   documento** (`protesto_certidao.onde_casa_o_devedor`, na certidão e no
   Livro de Protocolo a pedido escrito). O nome tem de ser igual ao gravado,
   sem acento, sem caixa e sem espaço a mais. Não basta estar contido nele: com
   o CPF, «SILVA» traria todos os SILVA sem documento. O homônimo que tem
   OUTRO documento continua de fora, e o nome continua sendo texto, e não
   curinga — F
   `test_a_certidao_pedida_com_o_cpf_acha_o_protesto_do_devedor_gravado_sem_documento`.
2. **O escrevente é avisado** de que o título entrou só pelo nome
   (`so_pelo_nome`): na tela de busca (com o apontamento do Livro de
   Protocolo que a autorização traz), no recado da emissão, na página da
   certidão e na auditoria. O teor da certidão não muda.

### Sem caminho (✗), para decidir

- **O protesto pago depois de lavrado** e **a sustação judicial precária** —
  respondidas pelo oficial em 21/10/2026 (LH13): **17 c** (depois do protesto
  lavrado não se paga na serventia; o caminho é o credor e a carta de
  anuência, e o legado PAGO com protesto em pé se cancela por anuência ou
  ordem judicial) e **18 a** (CNN art. 263-K: a ordem judicial leva a marca, e
  a provisória sai «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA»). Ficam para
  decidir: a relação diária às entidades (Lei 9.492, art. 29) continua sem o
  suspenso provisório; o arquivo de emolumentos da CENPROT não traz o legado
  PAGO com protesto em pé; a certidão só com sustação precária abre com a
  cabeça da positiva.

- **Gratuidade no protesto**: o envelope do selo do Protesto
  (`ato_selado.envelope_do_protesto`) não tem isenção. O item 17.8 da tabela
  (mandado judicial a beneficiário de assistência) não tem como selar
  gratuito. Confira no contrato do selador.
- **Livro de Registro de Protestos** como papel e **Livro de Índices** (CN-MA
  arts. 895 e 896): não há vista nem impressão.
- **Averbação do efeito suspensivo** no registro: só o ato, sem texto lavrado.

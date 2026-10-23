# Inventário dos papéis ainda montados no código

> Gerado no LF06A (19/10/2026). **Os próximos lotes (LF06B a LF06G) leem este
> arquivo**: cada um migra as linhas da sua seção, pelo passo a passo de
> [`MODELOS_PADRAO.md`](MODELOS_PADRAO.md), e marca a linha migrada com ✓.

## Como foi medido

Varredura do código em 19/10/2026, por atribuição, procurando montador de
texto que vai a papel (certidão, termo, intimação, edital, notificação, aviso,
recibo, etiqueta, livro, ofício, mensagem ao cliente): constantes, f-strings e
concatenações com CERTIFICO, INTIMA, NOTIFICA, EDITAL, «V. S.ª», «Dou fé»,
«Era o que», TERMO, AVISO, RECIBO… Ficaram de fora mensagem de tela (`flash`),
log, docstring e comentário. **A linha do código não está aqui de propósito** —
ela muda a cada lote; procure pela função ou constante.

Colunas: **forma** diz como o texto está montado hoje (constante inteira,
f-string de frases, template, mistura com regra); **observação** diz o que o
lote precisa saber — se uma REGRA jurídica decide a frase (ela fica no código;
o texto da frase vai como peça `<CHAVE>__<peca>.txt`), se o texto é CONGELADO
depois de expedido (texto expedido não muda: o ouro do lote tem de provar
isso), e as duplicações.

A varredura foi feita por leitura do código, e não por execução: antes de
migrar uma linha, o lote confere a função na árvore dele.

## Já migrados — LF06A ✓

Os **41 papéis do catálogo** (`modelos_papeis/`) saíram das constantes
`MODELO_*`/`TERMO_*` de catorze módulos para `modelos_padrao/`, com os mesmos
bytes (teste-ouro em `tests/test_modelos_da_casa.py`):

| ✓ | atribuição | chaves |
|---|---|---|
| ✓ | Registro de Imóveis | RI_CABECALHO, RI_FICHA, RI_CERTIDAO, RI_CERTIDAO_INTEIRO_TEOR, RI_CERTIDAO_ONUS, RI_CERTIDAO_PROPRIEDADE, RI_CERTIDAO_DOMINIAL, RI_CERTIDAO_VINTENARIA, RI_CERTIDAO_NEGATIVA_IMOVEL, RI_NOTA, RI_PRENOTACAO, RI_LIVRO3_FICHA, RI_LIVRO3_CERTIDAO |
| ✓ | Caixa e protocolo | CAIXA_RECIBO, CAIXA_ORCAMENTO, CAIXA_RECEPCAO |
| ✓ | Tabelionato de Notas | NOTAS_TRASLADO, NOTAS_TERMO_LIVRO, NOTAS_CERTIDAO_INTEIRO_TEOR, NOTAS_CERTIDAO_POSITIVA, NOTAS_CERTIDAO_NEGATIVA, NOTAS_CARTAO_FICHA |
| ✓ | RCPJ e RTD | RCPJ_CERTIDAO, RTD_CERTIDAO, RCPJ_TEOR_AVERBACAO, RCPJ_TEOR_REGISTRO, RTD_TEOR_AVERBACAO, RTD_TEOR_REGISTRO, RCPJ_CERTIDAO_CAPA, RTD_CERTIDAO_CAPA, RCPJ_CERTIDAO_FAIXA, RTD_CERTIDAO_FAIXA |
| ✓ | Registro Civil das Pessoas Naturais | RC_TERMO_NASCIMENTO, RC_TERMO_CASAMENTO, RC_TERMO_OBITO, RC_TERMO_LIVRO_E |
| ✓ | Protesto | PT_TERMO_PROTESTO, PT_INSTRUMENTO_PROTESTO, PT_CERTIDAO_NEGATIVA, PT_CERTIDAO_POSITIVA, PT_CERTIDAO_CANCELAMENTO |

Dois deles ainda são **esqueleto** — o texto que o papel afirma está numa
f-string do módulo, e não no padrão: `PT_CERTIDAO_POSITIVA` (`"{cabeca}
{corpo}"`) e a «cabeça» de `PT_CERTIDAO_CANCELAMENTO`. Estão na seção LF06E.
**LF06E ✓**: a cabeça é a peça `PT_CERTIDAO_CABECA`, editável na tela.

## Já migrados — LF06C ✓ (Registro Civil, 19/10/2026)

**Doze papéis novos no catálogo** e **155 peças** em `modelos_padrao/rcpn/`,
com os mesmos bytes do que o código montava (ouro por grupo de módulos em
`tests/fixtures/modelos_ouro/ouro_lf06c*.py`, gravado na árvore de antes):

| ✓ | papel | o que é |
|---|---|---|
| ✓ | RC_QUALIFICACAO | a ordem das partes da qualificação nos quatro termos (as frases são peças) |
| ✓ | RC_CERTIDAO_RESUMO | o fim do teor congelado da certidão em resumo (averbações, cancelado, fecho) |
| ✓ | RC_CERTIDAO_INTEIRO_TEOR | a introdução da certidão de inteiro teor |
| ✓ | RC_ANOTACAO_CRC_COMPACTA, _COMPLETA, _FE_PUBLICA | as três anotações sugeridas a partir da comunicação da CRC |
| ✓ | RC_AVERBACAO_RETIFICACAO | a averbação de retificação do art. 110 |
| ✓ | RC_COMUNICACAO_OBITOS | a comunicação mensal de óbitos |
| ✓ | RC_OFICIO_FUNAI | o ofício à FUNAI (art. 253 §2º) |
| ✓ | RC_EDITAL_PROCLAMAS, RC_EDITAL_PROCLAMAS_FOLHA | o teor oferecido do edital de proclamas e a folha impressa |
| ✓ | RC_CERTIDAO_HABILITACAO | a certidão de habilitação para casamento |

As frases que uma REGRA escolhe — as do termo, as linhas do prazo da
habilitação, as da averbação — são peças desses papéis e dos quatro
`RC_TERMO_*`. A seção LF06C abaixo diz, linha a linha, o que virou papel, o que
virou peça e o que ficou no código, e por quê.

## Fora deste inventário, de propósito

- **As minutas de escritura `nt_modelos`** (333 linhas no banco; semente em
  `notas_modelos.py`) — são o CORPO DO ATO, com os campos da CENSEC. Assunto
  próprio do **LF06D**; o LF06A não as tocou. ✓ LF06D: o padrão das 33 foi
  para `modelos_padrao/notas/minutas/`; o ajuste continua em `nt_modelos`.
- **`ri_modelos_atos.MODELOS`** — 25 minutas de ato do RI (mais
  `QUALIF_PF`/`QUALIF_PJ`/`COMUNS`), catálogo próprio. O **LF06B** decide se
  entram na base de padrões ou continuam como minuta.
- **`rc_modelos_livres`** — segundo catálogo, paralelo, de papéis avulsos do
  RCPN (corpos na tabela `rc_modelos_livres`). **O LF06C decidiu: fica fora
  da base.** É catálogo de CRIAÇÃO da casa — a casa escreve o corpo e dá o
  nome —, sem texto de fábrica que a base guardasse (nenhuma semente no
  código; uma linha na produção); «voltar ao padrão» e «o padrão mudou» não
  têm sentido ali; ele preenche os claros com `str.replace`, e não com o
  `str.format` da base; e nada do que ele imprime congela.
- **Os moldes `.odt` das certidões do RCPN** (`modelos/`, `modelos_moldes.py`,
  `mo_moldes`) — já são editáveis na tela de Modelos (enviar `.odt`). Se forem
  para a base, vão no formato `ODT` (o binário como está).
  **O LF06C não os levou**, e mediu por quê: o ajuste da casa já mora fora do
  pacote (`mo_moldes`) e a atualização já não o sobrescreve; a base daria só
  o aviso «o padrão mudou», que pede uma coluna `base_impressao` em
  `mo_moldes`; e o molde de fábrica é lido do disco por `rc_certidao_odt`, pela
  ferramenta `tools/moldes_do_civil.py`, pelo pacote público e por uma dúzia
  de testes. Fica para quando a tela de Modelos ganhar o aviso para os moldes.
- **`notas_selo.MODELO_PADRAO`** — é a URL de dentro do QR do selo, e não
  papel (ver `modelos_da_casa`).
- **`resolve_intimacao`** — citado na especificação do LF06A como papel
  montado no código, e conferido: `montar` monta só o JSON que vai à Central
  (`/api/batches/json`); o texto que o devedor recebe é escrito pela
  plataforma. Não há texto desta casa a migrar ali. Os papéis da intimação do
  protesto que SÃO desta casa (aviso, edital, canhoto) estão na seção LF06E.
- **Texto que ainda não vai a papel** — o `comprovante` da intimação e o
  `resumo` da não-entrega (`protesto_aviso`), as anotações automáticas do
  Livro 1 do RI e o dossiê da usucapião são registro interno; o lote decide se
  viram papel antes de levá-los à base.

## Achados da varredura que NÃO são migração

Medidos ao varrer e **não consertados aqui** (não são escopo do LF06A). Os três
primeiros foram conferidos no código pelo LF06A; os outros vêm da varredura e o
lote confere antes de mexer.

- `atrib_certidao.emitir` escolhe a chave do catálogo com `p["chave"] ==
  "RCPJ"`, mas o painel só tem `RCPJ_RTD` e `LIVRO3`: **toda certidão RCPJ/RTD
  usa o ajuste de `RTD_CERTIDAO`**, e um ajuste em `RCPJ_CERTIDAO` nunca é
  lido. (LF06F)
- A ficha de `PT_TERMO_PROTESTO` explica os marcadores `{base}` e
  `{posteriori}`, que o texto não tem mais (hoje são `{tipo}`, `{motivo}` e
  `{edital}`). (LF06E)
- `gestor_protesto._modelo_do_termo` procura «9.430» no termo, e nenhum padrão
  da pasta o tem: o alerta só acende com ajuste da casa. (LF06E)
- RCPN: a frase dos gêmeos não é montada a partir do assento (sai vazia);
  «Filho de»/«Sepultado em» no óbito ficam no masculino; a certidão em resumo e
  a certidão de habilitação são remontadas na impressão, e não lidas do teor
  congelado. (LF06C)
- Protesto: o fecho do cancelamento no plural sai «as BAIXAS e o
  CANCELAMENTOS»; a intimação digital vira «entregue no endereço do devedor»
  no instrumento e «intimado pessoalmente» no livro de protocolo. (LF06E)
- RCPJ/RTD: o teor gravado no livro (`atribuicoes_web.rcpj_rtd_lancar`) usa
  `rg_teor_rtdpj.intro`, e não o papel `*_TEOR_*` do catálogo — editar o modelo
  muda o PDF, e não o livro. (LF06F) **Resolvido no LF06F**: `intro` lê a ===INTRO=== do
  papel da série, com o ajuste da casa.
- A tela de Modelos recusa TODO papel em Jinja que use um claro que o boneco
  da conferência não tem (`modelos_web.ENSAIO`, `modelos_elementos._ENSAIO`:
  só `hoje`, `agora`, `sv`) — medido no LF06F: os padrões de CAIXA_RECIBO,
  CAIXA_ORCAMENTO, CAIXA_RECEPCAO, RI_NOTA, RI_PRENOTACAO, NOTAS_TRASLADO,
  NOTAS_TERMO_LIVRO… não passam na própria conferência, e a casa não grava nem
  o padrão de volta. O conferidor próprio do RI não basta: o
  `modelos_elementos.salvar` confere de novo com o boneco. O LF06F registrou
  conferidores pela montagem da emissão só para os papéis dele
  (`modelos_elementos.CONFERIDORES`); os outros lotes podem fazer o mesmo.
- O cabeçalho da serventia é montado em código em ~5 lugares diferentes (RI,
  RCPN, Notas, inteiro teor, ficha do Livro 3). Lembrar a decisão do oficial de
  07/09/2026 — «cabeçalho dos atos vamos deixar num ajuste separado para manter
  a forma e diminuir o risco de ir errado» — antes de migrar qualquer um deles.

### Achados do LF06C (Registro Civil) — medidos, mantidos byte a byte, não consertados

O ouro do LF06C prova que os papéis saem como saíam — inclusive com estes
defeitos, que são regra de negócio e ficam para quem decide:

- **Termos — concordância.** O óbito diz sempre «Filho de» e «Sepultado em»; o
  termo de nascimento diz «sendo filho de» também para a registrada; «casado(a)»,
  «representado(a) por seu(sua) tutor(a)» e «MM. Juiz(a)» não concordam.
- **Óbito — § 1º do art. 255.** Sem marca nenhuma, a declaração sai «…o declarante
  ignorava: era eleitor, deixou bens, deixou filhos e pessoa não identificada» —
  o rótulo da tela vira texto do termo.
- **Gêmeos.** A frase dos gêmeos continua sem quem a monte: sai vazia na lavratura.
- **Qualificação.** Data que não é ISO vira lixo («01/02/1990» → «nascido no dia
  90//1/01/0»); documento que não é RG nem CPF some calado.
- **Datas.** O mesmo termo de casamento escreve o casamento anterior e o pacto em
  dd/mm/aaaa; a certidão em resumo escreve «TRES» sem acento; a averbação de
  retificação escreve «9 de Outubro»; a comunicação de óbitos, a FUNAI e o resumo
  da anotação levam a data ISO crua (a FUNAI, com a hora).
- **Certidão em resumo.** Os rótulos dos atos saem sem acento («Averbacao:»,
  «Anotacao:», «Retificacao:»); «Ofício Único» era dado da casa escrito no código
  (agora está no `.txt` da introdução do inteiro teor, e a casa pode editá-lo).
- **Anotação da CRC.** Óbito sem nome sai «anoto o óbito de , na serventia…»; a
  comunicação de alterações de estado civil sai «anoto o alterações de estado
  civil… referente a casamento»; a de fé pública diz sempre «recebida da»; cidade
  com hífen no nome é cortada.
- **Averbação de retificação.** Campo sem artigo ganha «DE» («DA MÃE» → «DE DA
  MÃE»); sem cidade, o fecho sai «dou fé. , 19/10/2026.». **LGPD:** a docstring de
  `rc_averbacao_modelos.py` e `tests/test_rc_averbacao_modelos.py` têm nomes com
  cara de pessoa real — o ouro do LF06C não os usa.
- **Comunicação mensal de óbitos.** «falecido em» no masculino para mulher; «1
  anos»; a da Junta Militar lê «Comunicamos, relação dos óbitos…, os óbitos
  lavrados…»; a primeira linha é o nome do titular (`serventia_titular`), e não o
  da serventia; serventia com campo nulo imprime «None».
- **FUNAI.** «Livro: A» quando não há livro nenhum.
- **CPF averbado.** Ao regravar, as formas só-rótulo e só-nome perdem «referente…»;
  nome com «.» é cortado («MARIA S. DE EXEMPLO» → «MARIA S.»). E **a etiqueta da
  margem regrava `rc_atos.teor` num GET** (`sincronizar_teor_do_ato` na rota da
  etiqueta) — a regra da casa é «GET não grava».
- **Etiqueta da averbação.** Títulos sem acento; «Lavrado por:» no meio da linha
  não é reconhecido e a linha sai repetida.
- **Habilitação.** O aviso interno «Revisão jurídica local…» sai impresso no edital
  público (agora é um claro, e a casa pode tirá-lo em Modelos); a certidão de
  habilitação não congela e o hash da «Conferência» não cobre o texto — um ajuste
  da casa muda a reimpressão das já expedidas; os valores entram no HTML sem
  escape; com o prazo vazio sai «Prazo encerrado em — — sem oposição»; linha
  antiga com `edital_hash`/`certidao_hash` nulo dá erro 500 na impressão; a folha
  do edital é assinada sempre pelo titular.
- **`rc_modelos_livres`.** A conferência aceita «{ nome }», que a montagem não
  preenche; `{regime_de_bens}` sai em código cru.
- **Papel fora do inventário.** A comunicação para anotação em outra serventia
  (art. 106 / art. 367, «COMUNICAÇÃO PARA ANOTAÇÃO») é texto dentro do template
  de tela `rcpn_anotacao_oficio.html`; o resumo que ela leva (`rc_anotacao`) ficou
  no código. Separar o papel da tela é trabalho próprio.
- **O `content.xml` depende do processo.** `ri_odt.ESTILOS_EXTRA` é um registro
  global que o `notas_web` (ao registrar as rotas) e o `ri_odt` (no carimbo)
  completam: o mesmo papel sai com mais ou menos estilos conforme o que rodou
  antes. Não muda o texto; o ouro do LF06C compara o corpo do documento.

## LF06B — Registro de Imóveis (inclui Livro 3) (41 linhas)

> **LF06B, 19/10/2026:** ✓ migrada (a chave está na observação) · ⊘ fica no
> código, decidido, com o porquê · ☐ ficou para depois, com o motivo. As
> frases migradas são papéis do catálogo (`modelos_papeis/ri.py`, grupo
> LF06B), lidas por `ri_frases.py`; o ouro está em
> `tests/fixtures/modelos_ouro/lf06b_*.py`. 21 ✓ · 14 ⊘ · 6 ☐ (três ☐ do
> carimbo do selo viraram ⊘ quando o LF06G deixou o `selo_no_papel` no código).

| ☐ | módulo | função (ou constante) | atribuição | o que é | forma | observação |
|---|---|---|---|---|---|---|
| ☐ | ri_odt.py | cabecalho_certidao_completo_html (+_odf) | Registro de Imóveis | Timbre completo de toda certidão do RI por texto (República, «ESTADO DO MARANHÃO», Comarca, Serventia, endereço, titular, «— Substituta», CNS) | mistura com regra | Não usa RI_CABECALHO; calculado na impressão; também usado por `atribuicoes_web` (Livro 3 e outras). Estado fixo no código. **LF06B:** não migrado — a decisão do oficial de 07/09/2026 («cabeçalho dos atos vamos deixar num ajuste separado para manter a forma e diminuir o risco de ir errado») manteve a forma do timbre no código; para a casa decidir: um papel `RI_CABECALHO_CERTIDAO` com um `{% if %}` por linha, como o `RI_CABECALHO` |
| ☐ | ri_odt.py | cabecalho_certidao_compacto_html (+_odf) | Registro de Imóveis | Timbre compacto «Oficial: … · Substituta: …», «CNS … — Cidade/UF» | f-string de frases | Ficha do Livro 3 e `certidao_folhas`; terceiro desenho de cabeçalho. **LF06B:** não migrado — mesma decisão do oficial (07/09) que a linha acima |
| ☐ | ra_ficha_odt.py | cabecalho_ficha_livro3_odf | Registro de Imóveis | Grade do cabeçalho da ficha do Livro 3 | template html em f-string | Cópia à mão do RI_CABECALHO: editar o catálogo não muda o Livro 3. «Oficial Registrador(a)» fixo. **LF06B:** não migrado — mesma decisão do oficial (07/09) sobre o cabeçalho |
| ☐ | ri_schema.py | TIPOS_CERTIDAO | Registro de Imóveis | Nomes que viram o título impresso da certidão (`tipo_certidao_nome\|upper`) | constante inteira | «CERTIDÃO DOMINIAL / CADEIA DOMINIAL», com a barra. **LF06B:** não migrado — o mesmo nome é rótulo da tela (a lista de tipos) e título impresso; separar o título do rótulo muda a tela, e fica para a casa decidir |
| ✓ | ri_onus_ia.py | titulo | Registro de Imóveis | «Certidão positiva/negativa de ônus e … de registro de ações reais e pessoais reipersecutórias» | mistura com regra | O resultado decide a frase. **LF06B:** `RI_ONUS_TITULO` (positiva/negativa decididas no código) |
| ✓ | ri_digitalizacao.py | TITULO_CERTIDAO_REPROGRAFICA + corpo_resumo_digitalizacao | Registro de Imóveis | Corpo da certidão reprográfica («… por reprodução… sha256», «Era o que nela continha.») | f-string de frases | Congelado no hash; fecho repete o miolo RI_CERTIDAO_INTEIRO_TEOR. **LF06B:** em parte — o fecho é `RI_REPROGRAFICA_FECHO`; o título e os parágrafos do sha256 ficam no código porque `_fecho_html_para_papel` os tira do papel pela redação literal (editados, o sha256 iria ao papel do cliente) |
| ✓ | ri_digitalizacao.py | odt_da_digitalizacao (capa) | Registro de Imóveis | «Reprodução fiel da matrícula digitalizada (N páginas).» | f-string de frases | Montada na impressão, sem cabeçalho. **LF06B:** `RI_REPROGRAFICA_CAPA` (o plural de «página» fica no código). **LH02 (21/10/2026):** a capa saiu com o modelo da casa da substituta (produção 3.6.293.4); `RI_REPROGRAFICA_CAPA` passou a ser o CERTIFICO e a ressalva da folha 1, com a identificação do documento no claro (a regra que a monta, e as páginas por extenso, ficam no código) |
| ✓ | ri_digitalizacao.py | odt_da_digitalizacao (fecho do papel) | Registro de Imóveis | «Era o que constava no documento/assento reproduzido. Nada mais. Certifico e dou fé.» | frase | Montada na impressão; o fecho do livro (`RI_REPROGRAFICA_FECHO`) não se imprime. **LH02:** `RI_REPROGRAFICA_FECHO_DO_PAPEL`. Ficam no código o título «CERTIDÃO REPROGRÁFICA» (o nome do tipo, como `TITULO_CERTIDAO_REPROGRAFICA`), a qualificação de quem assina e o cabeçalho, que lê o cadastro da serventia como o `cabecalho_certidao_completo_html` (Estado fixo) |
| ⊘ | ri_digitalizacao.py | _fecho_html_para_papel | Registro de Imóveis | Filtro que tira do corpo congelado o título e o parágrafo do sha256 | regex sobre a redação | Depende da redação literal de `corpo_resumo_digitalizacao`. **LF06B:** fica no código: é regra (regex) sobre o título e o parágrafo do sha256, que por isso não foram para a base |
| ✓ | ri_web.py | ri_emitir_certidao (via digitalização) | Registro de Imóveis | «VALIDADE: 30 (trinta) dias … art. 53 … Dou fé.» da reprográfica | f-string de frases | Cópia literal do molde RI_CERTIDAO; «30» fixo, não lê `VALIDADE_CERTIDAO_DIAS`. Congelado. **LF06B:** `RI_REPROGRAFICA_VALIDADE` (o «30» continua escrito no texto, como antes) |
| ✓ | ri_web.py | clausula_html_prenotacoes_abertas | Registro de Imóveis | «CERTIFICO ainda que, nesta data, (não) há título(s) prenotado(s)… Prov. CNJ 149/2023» | mistura com regra | Há/não há e plural decididos no código; base legal no código. Congelado. **LF06B:** `RI_PRENOTACOES_ABERTAS_NAO_HA`, `_HA_UMA`, `_HA_VARIAS`, `_ITEM_PROTOCOLO`, `_ITEM_DATA`, `_ITEM_NATUREZA`, `_ITEM_OBJETO` (há/não há, plural e o que entra no item decididos no código) |
| ✓ | ri_certidao_negativa.py | montar_identificacao | Registro de Imóveis | «pelo documento X», «pelo nome «…»», «pela descrição do imóvel «…»» | mistura com regra | Entra no RI_CERTIDAO_NEGATIVA_IMOVEL. **LF06B:** `RI_NEGATIVA_CRITERIO_DOCUMENTO`, `_NOME`, `_IMOVEL`, e a quarta, «pelo bairro «…»», da rota da negativa: `RI_NEGATIVA_CRITERIO_BAIRRO` |
| ⊘ | ri_web.py | _contexto_da_cadeia | Registro de Imóveis | «atual» / «origem» em «Matrícula N.º X (origem)» | constante embutida | Congelado. **LF06B:** fica no código: «atual»/«origem» é o VALOR do campo `papel`, que a regra da cadeia usa; como ele sai no papel já se edita no `RI_CERTIDAO_DOMINIAL` (`({{ b.papel }})`) |
| ⊘ | ri_web.py | _assinatura_de_quem_emitiu / _corpo_ja_traz_quem_emitiu | Registro de Imóveis | Nome e função de quem expediu, no pé da certidão | mistura com regra | Heurística dos últimos 900 caracteres. **LF06B:** fica no código: não há frase — é o nome e a função GRAVADOS, em ODF, e a regra dos últimos 900 caracteres |
| ☐ | ri_web.py | ri_emitir_certidao_negativa / contexto_ficha | Registro de Imóveis | «Tabelião Registrador» / «Tabeliã Registradora Substituta» | mistura com regra | Repetido no RI_NOTA; gênero fixo. **LF06B:** não migrado — na ficha é o padrão das configurações `ri_titulo_registrador`/`ri_titulo_substituta` (a casa já o muda lá); na negativa está fixo |
| ⊘ | ri_odt.py | partes_do_carimbo / linhas_desenhadas / carimbos_do_ato | Registro de Imóveis | «SELO DIGITAL DO TJMA», «Confira em <link>», numeração | f-string | Duas convenções de numeração (« 1» × «1/2»). **LF06B:** fica no código — é o carimbo do selo, comum às atribuições (o desenho é do `ri_odt`, a régua do `selo_no_papel`), e ia junto com a linha do `selo_no_papel`, que o LF06G decidiu deixar no código: é o que o selo declara, e os desenhos são chamados sem conexão (uma peça ali seria lida só do padrão, e o ajuste da casa nunca chegaria) |
| ☐ | ri_web.py | _ROTULO_POR_PREFIXO / selos_do_ato_rotulados / contexto_ficha | Registro de Imóveis | «SELO DE PRENOTAÇÃO / ARQUIVAMENTO / ABERTURA / REGISTRO / AVERBAÇÃO» | mistura com regra | Repetidos na tela `ri_ficha`. **LF06B:** não migrado — os mesmos rótulos estão escritos à mão em quatro trechos de `registrar_rotas`, e a ordenação compara o literal «SELO DE PRENOTAÇÃO»: levar só o dicionário faria uma edição mudar metade dos carimbos da mesma ficha. Comparar pelo prefixo `PRENOT` e juntar os quatro antes de migrar |
| ⊘ | ri_web.py / ri_digitalizacao.py / ri_odt.py | ri_prenotacao_comprovante, ri_certidao_odt, odt_da_digitalizacao, carimbo_da_certidao_odf | Registro de Imóveis | «SELO DA PRENOTAÇÃO», «SELO DA CERTIDAO», «SELO DA CERTIDÃO» | constante | Inconsistentes (til, «DA» × «DE»). **LF06B:** fica no código — vai com os rótulos do carimbo (linha `partes_do_carimbo`), que ficaram no código com o `selo_no_papel` (LF06G) |
| ⊘ | ra_ficha_odt.py | _carimbos_odf_do_ato / contexto | Registro de Imóveis | «SELO DE AVERBACAO» (sem acento); linhas de partes e atos da ficha do Livro 3 | mistura com regra | O RI_LIVRO3_FICHA recebe `{atos}`/`{partes}` prontos. **LF06B:** fica no código — vai com os rótulos do carimbo (linha `partes_do_carimbo`), que ficaram no código com o `selo_no_papel` (LF06G) |
| ✓ | ri_web.py | ri_prenotacao_comprovante | Registro de Imóveis | «— prazo suspenso desde … (motivo); o limite avança…» dentro de `{{ limite }}` | mistura com regra | Contorna o RI_PRENOTACAO; motivos de `ri_prenotacao_prazo.MOTIVOS`. **LF06B:** `RI_PRENOTACAO_PRAZO_SUSPENSO` (quando está suspensa e o nome do motivo continuam no código) |
| ⊘ | ri_web.py | ri_nota_odt | Registro de Imóveis | Numeração «1. …» das exigências | f-string | O RI_NOTA recebe `exigencias_odf` pronto. **LF06B:** fica no código: a numeração «1.» é formato, e o texto de cada exigência já é da nota |
| ✓ | ri_web.py | fecho_do_ato | Registro de Imóveis | «Cidade/UF, <data>. Dou fé. O/A <título> (<nome>).» | mistura com regra | Omitido se o teor já diz «dou fé». **LF06B:** `RI_FECHO_DO_ATO` e `RI_FECHO_DO_ATO_SEM_TITULO` (sem data, sem nome ou teor que já diz «dou fé» → sem fecho, no código) |
| ✓ | ri_web.py | fecho_da_abertura | Registro de Imóveis | «… O referido é verdade e dou fé.» + linha + «NOME, função.» | mistura com regra | Segundo fecho, redação diferente. **LF06B:** `RI_FECHO_DA_ABERTURA`; a linha de assinar, o nome e a função ficam no código (a ordem é do oficial, 16/09) |
| ✓ | ri_web.py | modelos_de_encerramento | Registro de Imóveis | 5 teores de averbação de ENCERRAMENTO DA MATRÍCULA (CN arts. 426/427/495, Prov. COGEX 28/2026) | f-string de frases | Sugestão editável que vira ato e congela. **LF06B:** `RI_ENCERRAMENTO_TECNICA`, `_DESMEMBRAMENTO`, `_UNIFICACAO`, `_CIRCUNSCRICAO`, `_LIVRE` e o fecho `RI_ENCERRAMENTO_FECHO`, `_FECHO_SEM_TITULO`, `_FECHO_SEM_NOME` |
| ✓ | ri_web.py | ri_encerrar_matricula | Registro de Imóveis | «ENCERRAMENTO DESTA MATRÍCULA. MOTIVO: …» | f-string de frases | Vai direto ao livro; segunda redação. **LF06B:** `RI_ENCERRAMENTO_DIRETO` e `RI_ENCERRAMENTO_DIRETO_DESTINO` (o destino entra pela regra do código) |
| ✓ | ri_web.py | ri_cancelar_ato | Registro de Imóveis | «CANCELAMENTO DO ATO R-xx/… Nos termos do requerimento …» | f-string de frases | Direto ao livro. **LF06B:** `RI_CANCELAMENTO_DO_ATO` |
| ✓ | ri_indicador_lancamentos.py | registrar_cancelamento_livro2 / _livro3 | Registro de Imóveis | «CANCELAMENTO no Indicador Real/Pessoal. Fica anotado…» | mistura com regra | Quase cópia uma da outra. **LF06B:** `RI_CANCELAMENTO_INDICADOR_REAL`, `_PESSOAL`, `_PESSOAL_SEM_PARTES` e os três `RI_LIVRO3_CANCELAMENTO_INDICADOR_*` |
| ✓ | ra_registro.py | cancelar | Registro de Imóveis | «Cancelamento do registro. <motivo>» (Livro 3) | f-string | Congelado. **LF06B:** `RI_LIVRO3_CANCELAMENTO` |
| ✓ | ri_web.py | _contexto_modelo / ri_aplicar_modelo | Registro de Imóveis | Parte fixa das minutas: «PROTOCOLO N. x, DE …», «IMÓVEL: …», «[QUALIFICAR …]» | mistura com regra | Duas cópias quase iguais; terceira em `ri_cnib`. **LF06B:** `RI_MINUTA_PROTOCOLO` (uma chave só para as duas cópias da rota e o `ri_cnib`), `RI_MINUTA_IMOVEL` e `RI_MINUTA_IMOVEL_AREA`. Os `[MARCADORES]` ficam no código — e as duas cópias ainda divergem no do imóvel («[DESCREVER O IMÓVEL]» × «[DESCREVER]»), como antes |
| ✓ | ri_cnib.py | parte_fixa / teor_preparado | Registro de Imóveis | Protocolo, rótulo e junção «órgão — vara» da averbação de indisponibilidade | mistura com regra | Corpo vem de `ri_modelos_atos`. **LF06B:** em parte — a frase do protocolo é `RI_MINUTA_PROTOCOLO`, a mesma das minutas da ficha; os `[MARCADORES]` de campo que falta e o rótulo do ato ficam no código |
| ⊘ | ri_odt.py | rotulo_ato / html_com_destaque_rotulo_ato | Registro de Imóveis | «R-01/1234» e «**R-01/1234:-**» no teor da certidão | f-string | Congelado. **LF06B:** fica no código: é a numeração legal do ato (R-01/1234), não frase; `cabeca_do_ato` e o destaque dependem da forma |
| ⊘ | ri_lavrar_teor.py | MARCA_EMOLUMENTOS, MARCA_SELO, relacao_de_emolumentos, espaco_do_selo, frase_emolumentos_curta | Registro de Imóveis | «--- Emolumentos (calculados) ---», «Total R$ …» | constante + f-string | Hoje inativo; frase curta gravada em `ri_atos.emolumentos`. **LF06B:** fica no código: o que está ativo é `frase_emolumentos_curta` (ri_web), que grava um DADO curto em `ri_atos.emolumentos` com os rótulos «Total R$»/«Emol R$» — a régua dos valores do carimbo, que é a linha do `selo_no_papel` (LF06G); `MARCA_*`, `relacao_de_emolumentos` e `espaco_do_selo` não são chamados pelo `ri_web` |
| ✓ | ri_expurgo.py | texto_da_ata | Registro de Imóveis | Ata de ocorrência do expurgo (Livro 2) | f-string de frases | Congelada. **LF06B:** `RI_ATA_EXPURGO` |
| ✓ | ra_expurgo.py | compor_ata | Registro de Imóveis | Ata de ocorrência do Livro 3 («DESFEITO e devolvido …») | f-string de frases | Congelada; redação diferente do Livro 2. **LF06B:** `RI_LIVRO3_ATA_EXPURGO` (papel separado do Livro 2, de propósito) |
| ⊘ | ri_web.py | data_por_extenso / protocolo_data_cab | Registro de Imóveis | «19 de outubro de 2026» / «19 DE OUTUBRO DE 2026» | f-string | Usada em todos os papéis do RI e na usucapião. **LF06B:** fica no código: é o formato da data (os nomes dos meses), e não frase da casa |
| ⊘ | ri_prenotacao_prazo.py / ri_web.py | retomar / ri_protocolo | Registro de Imóveis | «Prazo suspenso de … a …», «[Encerrado] motivo» no Livro 1 | f-string | Hoje não impressas. **LF06B:** fica no código: anotação interna do Livro 1, hoje não impressa — não é papel |
| ⊘ | ra_selo.py / ri_web.py | referencia_do_ato / _selar_a_busca_da_certidao_do_ri | Registro de Imóveis | «AV - n do Registro X», «MATRICULA n» dentro do selo | f-string | Congelado no TJ. **LF06B:** fica no código: é o campo do selo enviado ao TJ (congelado lá), e não papel da casa |
| ⊘ | ri_modelos_atos.py | MODELOS (25 minutas), QUALIF_PF/QUALIF_PJ/COMUNS | Registro de Imóveis | Minutas de ato do RI | catálogo próprio | Não são papel da casa no sentido do catálogo; decidir no LF06B se entram. **LF06B:** ficam como catálogo de MINUTAS (decidido): cada uma traz requisitos e fundamentação que o código lê (`pendencias`) e é sugestão que o escrevente edita na lavratura — misturá-las com os padrões dos papéis juntaria duas coisas diferentes, como as `nt_modelos` das Notas (LF06D) |
| ✓ | atrib_certidao.py | corpo_por_reproducao | RI Livro 3 | «CERTIDÃO DE INTEIRO TEOR … por REPRODUÇÃO … sha256» | f-string de frases | Regra (`fonte_corpo == DIGITALIZACAO`). Congelado. **LF06B:** `RI_LIVRO3_REPRODUCAO` |
| ✓ | atrib_certidao.py | _bloco_atos_certidao_livro3 | RI Livro 3 | Miolo do claro `{atos}`: «AV-1 — dd/mm/aaaa:-», «(nenhum ato posterior informado)» | f-string | `cabeca_do_ato` depende da forma exata para pôr o selo. Congelado. **LF06B:** em parte — `RI_LIVRO3_SEM_ATOS`; a forma «AV-1 — dd/mm/aaaa:-» fica, porque `cabeca_do_ato`/`blocos_por_ato` a procuram no teor congelado para pôr o selo |
| ✓ | atribuicoes_web.py | _papel_da_certidao_do_livro3 | RI Livro 3 | ODT do Livro 3: título, «Era o que nela continha.», FINALIDADE, VALIDADE «30 (trinta) dias… art. 53…», «SELO DIGITAL DO TJMA» | f-string HTML | «30 (trinta)» à mão, embora `validade_de` leia de `ri_schema`. **LF06B:** em parte — o título, o aviso de cancelada e o fecho são `RI_LIVRO3_CERTIDAO_TITULO`, `RI_LIVRO3_CERTIDAO_CANCELADA` e `RI_LIVRO3_CERTIDAO_FECHO` (campo vazio não sai; o «30 (trinta)» continua no texto, como antes); o rótulo «SELO DIGITAL DO TJMA» vai com os do carimbo |
| ⊘ | atribuicoes_web.py | _assinatura_de_quem_expediu + «SELO DA CERTIDÃO» | RI Livro 3 | Nome/função de quem expediu, certidão por reprodução | f-string HTML | Duplicado de `ri_web._assinatura_de_quem_emitiu`. **LF06B:** fica no código: não há frase — é o nome e a função GRAVADOS, em ODF (como `_assinatura_de_quem_emitiu`); o rótulo «SELO DA CERTIDÃO» vai com os do carimbo |

## LF06C — Registro Civil das Pessoas Naturais (73 linhas)

> **LF06C, 19/10/2026:** ✓ migrada (o papel ou as peças estão na
> observação) ou removida por ser código morto · ⊘ fica no código, decidido,
> com o porquê — a mesma legenda do LF06B. 36 ✓ · 37 ⊘ · nenhum ☐. Os
> papéis estão em `modelos_papeis/rcpn.py`, lidos por `rc_textos.py`; o ouro,
> em `tests/fixtures/modelos_ouro/ouro_lf06c*.py`.

| ☐ | módulo | função (ou constante) | atribuição | o que é | forma | observação |
|---|---|---|---|---|---|---|
| ✓ | rc_termo.py | MODELO_TERMO_NASCIMENTO | Registro Civil das Pessoas Naturais | Termo de nascimento antigo (Jinja) | constante inteira | Código morto: nenhum lugar usa. Duplica o catálogo noutro formato ({{ }}); filiação na ordem pai/mãe, o contrário do catálogo **LF06C:** **Removido**: código morto — ninguém usava, e duplicava o catálogo em Jinja. |
| ✓ | rc_termo.py | MODELO_TERMO_OBITO | Registro Civil das Pessoas Naturais | Termo de óbito antigo (Jinja) | constante inteira | Código morto, duplicado do catálogo **LF06C:** **Removido**: código morto, duplicado do catálogo. |
| ✓ | rc_termo.py | MODELO_TERMO_CASAMENTO | Registro Civil das Pessoas Naturais | Termo de casamento antigo (Jinja) | constante inteira | Código morto, duplicado do catálogo; `contexto()` (258) também sem quem chame **LF06C:** **Removido**: código morto, junto com `contexto()`, `_pessoas_por_papel` e `_juntar_avos`, que só serviam a ele. |
| ⊘ | rc_termo.py | qualificacao | Registro Civil das Pessoas Naturais | Frase de qualificação da pessoa («portador(a) do RG…, residente e domiciliado(a)…») | f-string de frases | Duplicada e com regra diferente de `qualificacao_inteira` («(a)» em vez de concordar). Usada pelos papéis avulsos de `rc_modelos_livres` **LF06C:** **Fica no código**: preenche os claros dos papéis avulsos de `rc_modelos_livres`, que ficam fora da base (ver a linha dele). |
| ⊘ | rc_termo.py | completar_quem_assina / _trocar_o_traco | Registro Civil das Pessoas Naturais | «Eu, ___, Oficial, dou fé» no termo digitado | mistura com regra | Mexe no texto antes de congelar; a moldura vem do corpo do catálogo **LF06C:** **Fica no código**: não tem redação própria; a moldura é o corpo do `RC_TERMO_*`. |
| ⊘ | rc_modelos_do_livro.py | montar_do_formulario + O_TRACO_DA_CASA | Registro Civil das Pessoas Naturais | Motor que preenche o termo | mistura com regra | Regra: campo exigido vazio vira «____________»; frase opcional vazia some — fica no código **LF06C:** **Fica no código**: regra; o traço é marca relida (`completar_quem_assina`, `MARCAS_DE_RASCUNHO`). |
| ⊘ | rc_modelos_do_livro.py | limpar | Registro Civil das Pessoas Naturais | Normalização do termo (texto corrido) | regra | Art. 795 §2º — fica no código **LF06C:** **Fica no código**: regra do art. 795 §2º. |
| ⊘ | rc_modelos_do_livro.py | data_do_termo / por_extenso_com_algarismo | Registro Civil das Pessoas Naturais | Data do termo «dezenove (19) de agosto de … (2026)» | f-string | Um de 4 formatos de data por extenso no RCPN (rc_certidao 182, rc_averbacao_modelos 79, rc_modelos_livres 173) **LF06C:** **Fica no código**: regra de formato (o motor confere a igualdade). |
| ✓ | rc_modelos_do_livro.py | qualificacao_inteira | Registro Civil das Pessoas Naturais | Qualificação das partes no termo | f-string de frases | Concorda com o sexo e omite o que falta — regra fica no código, frases viram peça **LF06C:** → papel **RC_QUALIFICACAO** (a ordem das partes) + peças `__rg_`/`__cpf_`/`__nascimento_`/`__residencia_` `{masculino,feminino}` e `__naturalidade`; a concordância e a omissão ficam no código; na lavratura é lida pela busca única (`rc_textos.lendo_da_casa`). |
| ✓ | rc_modelos_do_livro.py | valores_do_assento | Registro Civil das Pessoas Naturais | Frases ocasionais do termo de nascimento (DNV, hora, cor, filiação 2, idade da mãe, avós, naturalidade, matrícula) | mistura com regra | Default fixo «Maranhão»/«MA» quando a serventia vem vazia (1040–1041) **LF06C:** → peças RC_TERMO_NASCIMENTO__dnv, __hora, __hora_cheia, __cor, __filiacao2, __idade_da_mae, __avos, __avos_de_um_lado, __naturalidade, __matricula; «Maranhão»/«MA», «Masculino»/«Feminino» e o `<strong>` ficam no código. |
| ⊘ | rc_modelos_do_livro.py | frase_gemeos (claro) | Registro Civil das Pessoas Naturais | Frase dos gêmeos (arts. 233 III e 234) | sem montador | O claro diz que vem de `gemeo_ordem`, mas nada a passa a `valores_do_assento`: na lavratura pelo assento sai sempre vazia **LF06C:** **Nada a migrar**: não há quem monte a frase (achado mantido). |
| ✓ | rc_modelos_do_livro.py | FRASE_PRIMEIRO_REGISTRO / frase_do_cpf / completar_teor_nascimento | Registro Civil das Pessoas Naturais | «Trata-se de primeiro registro.» e «Inscrito(a) no CPF n.º …» | constante + regra | Concorda com o sexo; fora em EOFICIO/ACERVO ou NATIMORTO **LF06C:** → peças RC_TERMO_NASCIMENTO__primeiro_registro, __cpf_masculino, __cpf_feminino (o nome antigo responde pelo `__getattr__`); o CPF já escrito se acha pelo número, e não pela frase. |
| ✓ | rc_modelos_do_livro.py | frase_dos_nomes | Registro Civil das Pessoas Naturais | Nome que cada cônjuge passa a usar | mistura com regra | Plural: ninguém mudou / um / os dois («respectivamente») **LF06C:** → peças RC_TERMO_CASAMENTO__nomes_mantidos, __nome_de_um, __nomes_dos_dois. |
| ✓ | rc_modelos_do_livro.py | relacao_de_documentos | Registro Civil das Pessoas Naturais | Documentos da habilitação no termo de casamento | mistura com regra | Separa apresentados de dispensados **LF06C:** → peças RC_TERMO_CASAMENTO__documentos_apresentados (também no digitado) e __documentos_dispensados. |
| ⊘ | rc_modelos_do_livro.py | regime_por_extenso | Registro Civil das Pessoas Naturais | Regime de bens por extenso | regra (hc_schema.REGIMES) | Mesma tabela da certidão, em minúscula **LF06C:** **Fica no código**: tabela `hc_schema.REGIMES`. |
| ✓ | rc_modelos_do_livro.py | valores_do_casamento | Registro Civil das Pessoas Naturais | Habilitação de outra serventia, proclamas, conversão de união estável, testemunhas, filiações | mistura com regra | — **LF06C:** → peças RC_TERMO_CASAMENTO__habilitacao_de_fora, __habilitacao_de_fora_proclamas, __conversao. |
| ✓ | rc_modelos_do_livro.py | frase_do_casamento_anterior / frase_do_pacto / frase_do_casamento_dos_pais | Registro Civil das Pessoas Naturais | Cônjuge anterior, pacto antenupcial, casamento dos pais | f-string de frases | «casado(a)» sem concordar **LF06C:** → peças RC_TERMO_CASAMENTO__casamento_anterior[_dissolvido], __pacto_data, __pacto_serventia, __pacto_data_serventia e RC_TERMO_NASCIMENTO__pais_casados_lugar, __pais_casados_cartorio, __pais_casados_lugar_cartorio; «casado(a)» mantido. |
| ✓ | rc_modelos_do_livro.py | frase_dos_ignorados | Registro Civil das Pessoas Naturais | Declaração do art. 255 §1º («o declarante ignorava: …») | mistura com regra | Usa o rótulo de tela de `rc_marcas_do_obito` como texto do termo **LF06C:** → peça RC_TERMO_OBITO__ignorados; os itens continuam os rótulos de `rc_marcas_do_obito` (achado). |
| ✓ | rc_modelos_do_livro.py | frase_do_conjuge_do_falecido / frase_dos_filhos_do_falecido / frase_dos_herdeiros | Registro Civil das Pessoas Naturais | Cônjuge sobrevivente ou pré-morto, filhos, herdeiros menores | mistura com regra | Três ramos de redação **LF06C:** → peças RC_TERMO_OBITO__estado_civil, __conjuge_sobrevivente, __conjuge_pre_morto, __deixou_conjuge, __teve_conjuge, __casamento_do_conjuge, __filhos, __herdeiros_sim, __herdeiros_nao. |
| ✓ | rc_modelos_do_livro.py | valores_do_obito | Registro Civil das Pessoas Naturais | Frases do óbito (filiação, DO, causa, sepultamento, eleitor, bens, filhos, testamento) | mistura com regra | «Filho de» (1518) e «Sepultado em» (1551) sempre no masculino **LF06C:** → peças RC_TERMO_OBITO__hora, __hora_cheia, __filiacao, __desconhecido, __declaracao_de_obito, __causa, __atestante, __sepultamento, __eleitor_sim/_nao, __bens_sim/_nao, __filhos_sim/_nao, __testamento; «Filho de»/«Sepultado em» mantidos no masculino (achado). |
| ✓ | rc_modelos_do_livro.py | _do_titulo / _filiacao_curta | Registro Civil das Pessoas Naturais | Título do Livro E e «filho/filha de» | f-string de frases | Aqui a filiação concorda com o sexo **LF06C:** → peças RC_TERMO_LIVRO_E__sentenca, __juizo, __juiz_do_juizo, __juiz, __processo, __transito, __escritura, __escritura_livro, __escritura_folha, __escritura_notas, __termo_declaratorio, __filho_de, __filha_de; « em {data}» fica no código. |
| ✓ | rc_modelos_do_livro.py | frase_do_livro_e | Registro Civil das Pessoas Naturais | Frase de cada espécie do Livro E | mistura com regra | Arts. 90, 92, 94, 94-A e 32 §4º **LF06C:** → peças RC_TERMO_LIVRO_E__<espécie> (as seis cabeças) + uma por cláusula (nascimento_registrado, casado_com, casamento_registrado, representado_pelo_tutor, requerimento, causa, curador/curadora/tutor/tutora nomeado(a), limites, internacao, tempo_de_ausencia, promovido_por, reconhecida, inicio, regime, registros_de_nascimento, anteriores, novo_nome). |
| ⊘ | rc_modelos_do_livro.py | valores_livro_e_do_assento | Registro Civil das Pessoas Naturais | Título, qualificação do titular e observações | mistura com regra | Default «Maranhão»/«MA» fixo **LF06C:** **Fica no código**: os padrões são dado; o título vem de `rc_cabecalho`. |
| ⊘ | rc_cabecalho.py | PAIS / TITULO_DO_ATO | Registro Civil das Pessoas Naturais | «REPÚBLICA FEDERATIVA DO BRASIL» e título de cada espécie | constante inteira | Folha do livro e termo do Livro E **LF06C:** **Fica no código**: cabeçalho apartado por decisão do oficial (07/09/2026, `CABECALHO_FICOU_DE_FORA`); TITULO_DO_ATO é tabela de rótulos. |
| ⊘ | rc_cabecalho.py | montar | Registro Civil das Pessoas Naturais | Cabeçalho da folha do livro | f-string | Um de ~5 cabeçalhos de serventia montados em código; decisão do oficial (07/09) de mantê-lo em código — confirmar antes de migrar **LF06C:** **Fica no código**: a mesma decisão do oficial (07/09/2026). |
| ⊘ | rc_folha.py | COLUNAS (títulos) | Registro Civil das Pessoas Naturais | Títulos impressos na folha | constante | Papel do livro **LF06C:** **Fica no código**: geometria da folha. |
| ⊘ | rc_folha.py | ASSINAM_ALEM_DE_QUEM_LAVROU | Registro Civil das Pessoas Naturais | Rótulos das linhas de assinatura | constante | Varia pela espécie **LF06C:** **Fica no código**: tabela de quem assina por espécie (regra). |
| ⊘ | rc_certidao.py | MODELOS (títulos) / SEM_DADO / SEM_INFORMACAO | Registro Civil das Pessoas Naturais | «CERTIDÃO DE NASCIMENTO»…; «ND», «SEM INFORMAÇÃO» | constante | Títulos duplicados em rc_certidao_inteiro_teor.TITULOS (56) **LF06C:** **Fica no código**: rótulos do leiaute CNJ; o quadro lê SEM_INFORMACAO. |
| ⊘ | rc_certidao.py | data_por_extenso | Registro Civil das Pessoas Naturais | Data da certidão em maiúsculas | f-string | Formato diferente do termo **LF06C:** **Fica no código**: regra de data. |
| ⊘ | rc_certidao.py | montar_teor (rótulos e linhas) | Registro Civil das Pessoas Naturais | Teor da certidão em resumo | mistura com regra | Congela em `rc_certidoes.teor` com hash **LF06C:** **Fica no código**: leiaute CNJ medido nas 145 certidões; o fim do teor virou RC_CERTIDAO_RESUMO. |
| ✓ | rc_certidao.py | montar_teor: «OBSERVAÇÕES/AVERBAÇÕES A ACRESCER» | Registro Civil das Pessoas Naturais | Averbações, «NADA CONSTA.», «Lavrado por:», «Selo:» | mistura com regra | «Lavrado por:»/«Selo:» duplicado em rc_etiqueta_averbacao **LF06C:** → papel **RC_CERTIDAO_RESUMO** + peça RC_CERTIDAO_RESUMO__nada_consta; «Lavrado por:»/«Selo:» e o rótulo do ato ficam no código (marcas relidas). |
| ✓ | rc_certidao.py | montar_teor: assento cancelado | Registro Civil das Pessoas Naturais | «CERTIFICO ainda que o referido assento encontra-se CANCELADO…» | constante | Duplicado em rc_certidao_quadro:101 **LF06C:** → peça RC_CERTIDAO_RESUMO__cancelado — a mesma que `rc_certidao_quadro` lê. |
| ✓ | rc_certidao.py | montar_teor: fecho | Registro Civil das Pessoas Naturais | «O referido é verdade e dou fé. …» | f-string | Mesmo fecho da averbação (rc_averbacao_modelos:244) **LF06C:** → papel RC_CERTIDAO_RESUMO (`{casa}`, `{onde}`, `{data}`). |
| ⊘ | rc_certidao.py | regime_da_certidao | Registro Civil das Pessoas Naturais | Regime de bens em maiúsculas | regra | — **LF06C:** **Fica no código**: regra (`hc_schema.REGIMES`). |
| ⊘ | rc_certidao_quadro.py | quadro_da_certidao | Registro Civil das Pessoas Naturais | Papel impresso da certidão em resumo | mistura com regra | Remonta do assento a cada impressão, e não do teor congelado **LF06C:** **Fica no código** (dado do assento); a frase do cancelado passou a ler a peça RC_CERTIDAO_RESUMO__cancelado. |
| ⊘ | rc_certidao_quadro.py | _genitores_nascimento / _quadro_casamento / _quadro_obito | Registro Civil das Pessoas Naturais | Genitores, cônjuges e falecido | mistura com regra | Default «Brasileira» **LF06C:** **Fica no código**: dado do assento; «Brasileira» é padrão de dado (achado). |
| ⊘ | rc_certidao_odt.py | valores | Registro Civil das Pessoas Naturais | Preenche os `@marcadores` dos moldes `.odt` | mistura com regra | «Não há.» como padrão **LF06C:** **Fica no código**: preenche os `@marcadores`; o papel editável é o molde .odt (ver «Fora deste inventário»). |
| ⊘ | rc_certidao_inteiro_teor.py | TITULOS / NOME_DA_ESPECIE | Registro Civil das Pessoas Naturais | «CERTIDÃO DE INTEIRO TEOR DE …» | constante | — **LF06C:** **Fica no código**: vocabulário de `{titulo}`/`{especie}`; `_paragrafos_html` acha o título pelo prefixo. |
| ✓ | rc_certidao_inteiro_teor.py | introducao | Registro Civil das Pessoas Naturais | «CERTIFICO E DOU FÉ que, a pedido de parte interessada, revendo os livros…» | f-string de frases | Traz fixo «Ofício Único» (dado da casa no código). Congela no teor **LF06C:** → papel **RC_CERTIDAO_INTEIRO_TEOR** + peças __com_o_seguinte_teor / __reprografica (a modalidade escolhe); «Ofício Único» foi para o .txt, e a casa pode editá-lo. |
| ⊘ | rc_certidao_inteiro_teor.py | entre_aspas / _ponto_no_teor_aspas | Registro Civil das Pessoas Naturais | Teor entre «» com ponto final | regra | — **LF06C:** **Fica no código**: regra tipográfica. |
| ⊘ | rc_certidao_inteiro_teor.py | SEPARADOR_ATOS_INTEIRO / completar_teor_colado_com_atos | Registro Civil das Pessoas Naturais | Averbações de `rc_atos` que faltam no teor colado | mistura com regra | — **LF06C:** **Fica no código**: separador e regra dos atos que faltam. |
| ⊘ | rc_certidao_inteiro_teor.py | montar_teor_repro | Registro Civil das Pessoas Naturais | «[Cópia reprográfica do assento anexa a esta certidão.]» | constante | — **LF06C:** **Fica no código**: a marca é lida de volta por regex em `html_da_certidao_repro`. |
| ⊘ | rc_certidao_inteiro_teor.py | _cabecalho_notas_html | Registro Civil das Pessoas Naturais | Cabeçalho da certidão | f-string | Montado na impressão **LF06C:** **Fica no código**: cabeçalho (decisão do oficial, 07/09/2026). |
| ⊘ | rc_certidao_inteiro_teor.py | _rodape_html | Registro Civil das Pessoas Naturais | Cidade-UF, data, quem emitiu, selo | f-string | — **LF06C:** **Fica no código**: data e quem assina, sem prosa. |
| ✓ | rc_certidao_inteiro_teor.py | _com_fecho_certificar | Registro Civil das Pessoas Naturais | «Era o que cabia certificar.» | constante | Fora do teor congelado **LF06C:** → peça RC_CERTIDAO_INTEIRO_TEOR__fecho. |
| ✓ | rc_certidao_inteiro_teor.py | html_da_certidao_texto / html_da_certidao_repro | Registro Civil das Pessoas Naturais | «CERTIDÃO CANCELADA — {motivo}» | f-string | — **LF06C:** → peça RC_CERTIDAO_INTEIRO_TEOR__cancelada; a moldura HTML e o escape ficam no código. |
| ⊘ | rc_anotacao_crc.py | MODELOS / ASSINATURA_PADRAO | Registro Civil das Pessoas Naturais | 3 modelos de anotação da CRC; «_____, Escrevente Autorizado (a)» | constante | O traço contraria o relato #63 **LF06C:** **Fica no código**: rótulos da tela e valor-padrão da assinatura. |
| ✓ | rc_anotacao_crc.py | _texto_compacto | Registro Civil das Pessoas Naturais | «ANOTAÇÃO: Aos {data}, anoto o …» | mistura com regra | — **LF06C:** → papel **RC_ANOTACAO_CRC_COMPACTA** + peças __ocorrido_em, __registrado_sob, __lavrado_sob, __na_serventia, __referente_a, __comunicacao_de. |
| ✓ | rc_anotacao_crc.py | _texto_completo | Registro Civil das Pessoas Naturais | «Comunicação de …: Código …» + «Eu, …, que anotei.» | f-string | — **LF06C:** → papel **RC_ANOTACAO_CRC_COMPLETA** + peça __origem. |
| ✓ | rc_anotacao_crc.py | _texto_fe_publica | Registro Civil das Pessoas Naturais | «ANOTAÇÃO: Conforme comunicação recebida da … CRC … Dou fé.» | f-string de frases | — **LF06C:** → papel **RC_ANOTACAO_CRC_FE_PUBLICA** + peças __ocorrido_em, __lavrado_em. |
| ⊘ | rc_anotacao_crc.py | _extrair_bloco / _titulo_humano | Registro Civil das Pessoas Naturais | «{n1} passou a assinar {novo}» | f-string | — **LF06C:** **Fica no código**: leitura do texto da CRC («passou a assinar» é eco da Central) e vocabulário. |
| ✓ | rc_averbacao_modelos.py | FUNDAMENTO_PADRAO / ABERTURA_DE_OFICIO | Registro Civil das Pessoas Naturais | Fundamento e abertura de ofício | constante | — **LF06C:** → peças RC_AVERBACAO_RETIFICACAO__fundamento e __de_oficio (os nomes antigos respondem pelo `__getattr__`). |
| ✓ | rc_averbacao_modelos.py | _uma_correcao / _PARTICIPIO / _titulo / _do_elemento | Registro Civil das Pessoas Naturais | «… foi grafada erroneamente como …»; «RETIFICAÇÃO DO/DA …» | mistura com regra | Concordância pelo artigo digitado **LF06C:** → peças RC_AVERBACAO_RETIFICACAO__uma, __uma_sem_artigo, __varias, __item, __item_sem_artigo, __titulo; a concordância pelo artigo fica no código. |
| ✓ | rc_averbacao_modelos.py | _abertura | Registro Civil das Pessoas Naturais | De ofício ou a requerimento | mistura com regra | — **LF06C:** → peças RC_AVERBACAO_RETIFICACAO__de_oficio, __a_requerimento, __data_do_requerimento. |
| ✓ | rc_averbacao_modelos.py | _teor_retificacao | Registro Civil das Pessoas Naturais | Averbação inteira de retificação (art. 110) | f-string de frases | Vai para `rc_atos.teor` **LF06C:** → papel **RC_AVERBACAO_RETIFICACAO** + peças __conforme, __constar, __assinatura, __assinatura_sem_funcao; a tela lê pela busca única. |
| ✓ | rc_averbacao_modelos.py | _prova_sugerida | Registro Civil das Pessoas Naturais | Sugestão de prova | f-string | — **LF06C:** → peças RC_AVERBACAO_RETIFICACAO__prova_termos_vizinhos, __prova_termo, __prova_data_de_nascimento. |
| ✓ | rc_averbacao_modelos.py | _montar_data_registro / _montar_erro_material | Registro Civil das Pessoas Naturais | Fundamento (art. 110) | f-string | — **LF06C:** → peça RC_AVERBACAO_RETIFICACAO__constar_data_registro; o `fundamento` de `rc_atos` é da tela e fica no código. |
| ⊘ | rc_cpf.py | texto_averbacao | Registro Civil das Pessoas Naturais | «Averbo neste assento o CPF n. …» | mistura com regra | — **LF06C:** **Fica no código**: a frase é lida de volta em sete lugares (detecção, CPF, referente, etiqueta, duplicata, re-selo, ficha). |
| ⊘ | rc_cpf.py | reescrever_teor_cpf | Registro Civil das Pessoas Naturais | Reconstrói o teor da averbação de CPF | regra | O texto muda depois de lavrado **LF06C:** **Fica no código**: regra que reescreve o teor a partir da frase relida (achados abaixo). |
| ⊘ | rc_etiqueta_averbacao.py | teor_com_lavratura / teor_com_selo | Registro Civil das Pessoas Naturais | «Lavrado por: …» / «Selo: …» | f-string | Duplicado em rc_certidao:600–603 **LF06C:** **Fica no código**: «Lavrado por:»/«Selo:» são marcas relidas. |
| ⊘ | rc_etiqueta_averbacao.py | arquivo_odt | Registro Civil das Pessoas Naturais | Etiqueta da margem (.odt) | f-string + XML | Títulos sem acento **LF06C:** **Fica no código**: XML do ODT; os títulos são o código do tipo do ato. |
| ⊘ | rc_assento.py | _lancar_no_assento | Registro Civil das Pessoas Naturais | «Lavrado por:» no teor | regra | — **LF06C:** **Fica no código**: só aplica a marca «Lavrado por:». |
| ⊘ | rc_anotacao.py | resumo_do_assento | Registro Civil das Pessoas Naturais | Resumo do assento para comunicação a outra serventia (art. 367) | f-string | Espécie em código e datas ISO cruas **LF06C:** **Fica no código**: preenche `{{ resumo }}` de `rcpn_anotacao_oficio.html`, e o papel é o template (ver «Achados»). |
| ✓ | rc_comunicacoes.py | DESTINOS / montar | Registro Civil das Pessoas Naturais | Comunicação mensal de óbitos | f-string de frases | Congela em `registrar_envio` (386) **LF06C:** → papel **RC_COMUNICACAO_OBITOS** + peças __sem_nome, __termo, __livro, __falecido_em, __idade, __sem_idade, __cpf, __declaracao_de_obito, __matricula, __nada_consta; DESTINOS fica (dado da norma, entra como claro). |
| ✓ | rc_funai.py | montar | Registro Civil das Pessoas Naturais | Ofício à FUNAI (art. 253 §2º) | f-string de frases | Congela com hash **LF06C:** → papel **RC_OFICIO_FUNAI** + peças __completar, __completar_nome, __completar_folha, __completar_matricula, __completar_etnia, __completar_aldeia. |
| ⊘ | rc_pedidos.py | _averbacoes | Registro Civil das Pessoas Naturais | Campo `averbacao_anotacao` da certidão eletrônica CRC | concatenação | — **LF06C:** **Fica no código**: formato do JSON para a CRC Central, e não papel desta casa. |
| ⊘ | rc_modelos_livres.py | CLAROS_COMUNS / CLAROS_* / _qualificacao | Registro Civil das Pessoas Naturais | Claros dos papéis avulsos (Termo de Gêmeos…) | mistura com regra | Segundo catálogo, paralelo (tabela `rc_modelos_livres`) **LF06C:** **Fica fora da base**: catálogo de criação da casa, sem texto de fábrica (preenchido por `str.replace`; nada congela). |
| ✓ | habilitacao_web.py | _modelo_do_edital | Registro Civil das Pessoas Naturais | Edital de proclamas: «Faço saber que pretendem casar-se…» | f-string de frases | Congela em `habilitacao.publicar_edital` (hash) **LF06C:** → papel **RC_EDITAL_PROCLAMAS** (montador `teor_sugerido_do_edital`, lido na ficha pela busca única). |
| ✓ | habilitacao_web.py | rcpn_habilitacao_edital (html) | Registro Civil das Pessoas Naturais | Moldura do edital .odt | f-string HTML | Imprime o aviso interno `AVISO_REVISAO_JURIDICA_HC` **LF06C:** → papel **RC_EDITAL_PROCLAMAS_FOLHA**; o cabeçalho e a «Conferência» ficam no código; o aviso interno virou o claro `{aviso_de_revisao_juridica}`. |
| ✓ | habilitacao_web.py | rcpn_habilitacao_certidao (html) | Registro Civil das Pessoas Naturais | Certidão de habilitação «CERTIFICO que, cumpridas as formalidades…» | mistura com regra | Remontada na impressão **LF06C:** → papel **RC_CERTIDAO_HABILITACAO** + peças __prazo_encerrado[_sem_oposicao], __prazo_em_curso[_sem_oposicao]. |
| ⊘ | hc_schema.py | ONDE_SE_PUBLICA / AVISO_REVISAO_JURIDICA_HC / DOCUMENTOS_DA_HABILITACAO / REGIMES | Registro Civil das Pessoas Naturais | Textos que entram no edital, termo e certidão | constante | — **LF06C:** **Fica no código**: fato da casa e aviso da tela (entram como claros), checklist copiado para `hc_documentos`, tabela código→rótulo. |
| ✓ | templates/rcpn_certidao_impressa.html | (template) | Registro Civil das Pessoas Naturais | Fecho «O Conteúdo da Certidão é verdadeiro. Dou fé.» e rótulos do quadro | template html | Diferente do teor congelado **LF06C:** **Removido**: template morto — nenhuma rota o desenhava. |
| ⊘ | templates/rcpn_folha_impressa.html / rcpn_modelo_documento.html | (template) | Registro Civil das Pessoas Naturais | Folha do livro e documento avulso impressos | template html | Varredura própria no LF06C **LF06C:** **Fica no código**: a folha é cabeçalho (decisão de 07/09/2026) e geometria; o documento avulso imprime o texto da casa (`rc_modelos_livres`). |

## LF06D — Tabelionato de Notas (25 linhas) — migrado em 19/10/2026

O LF06D conferiu cada linha na árvore dele (commit 2c41e90) antes de mexer, e
gravou o ouro de todas (`tests/fixtures/modelos_ouro/ouro_lf06d.py`): 217 saídas
dos montadores, as 33 minutas e os dois textos de dentro das rotas. **22 linhas
migradas (✓) e 3 que ficam no código (⊘)**, cada uma com o porquê — a
legenda do LF06B e do LF06C. Os papéis novos estão em `modelos_padrao/notas/`;
as frases que a regra escolhe são **peças** (`<CHAVE>__<peca>`), cada uma com a
ficha dela dizendo quando entra.

| ✓ | módulo | função (ou constante) | atribuição | o que é | forma | observação |
|---|---|---|---|---|---|---|
| ✓ | notas_schema.py | texto_reconhecimento | Notas | «RECONHEÇO POR SEMELHANÇA/AUTENTICIDADE A FIRMA … DOU FÉ.» | mistura com regra (espécie, plural, sinal) | **NOTAS_RECONHECIMENTO_SEMELHANCA** e **NOTAS_RECONHECIMENTO_AUTENTICIDADE**, com as peças `__firmas` e `__sinal`; a regra fica. Congelado em `nt_reconhecimentos.texto`; com sinal público e vários nomes continua no singular (regra intocada) |
| ✓ | notas_schema.py | texto_reconhecimento_sinal | Notas | «RECONHEÇO O SINAL PÚBLICO DE … DOU FÉ.» | f-string | **NOTAS_RECONHECIMENTO_SINAL**. Congelado |
| ✓ | notas_schema.py | TIPOS_AUTENTICACAO / texto_autenticacao | Notas | «AUTENTICO E DOU FÉ QUE A CÓPIA É A REPRODUÇÃO FIEL…» | constante inteira | **NOTAS_AUTENTICACAO** e **NOTAS_AUTENTICACAO_INTERNET**; o item da tabela fica no código (`AUTENTICACOES`). Congelado em `nt_autenticacoes` |
| ✓ | notas_schema.py | FECHO_ETIQUETA / texto_da_etiqueta | Notas | «EM TEST. DA VERDADE. CIDADE-UF,dd/mm/aaaa.» | mistura com regra | **NOTAS_ETIQUETA_FECHO** (+ peça `__local_e_data`). `modelos_motor_etiqueta.texto_da_etiqueta_motor` embrulha a mesma função e passa `con`. O «DA VERDADE» que reconhece a etiqueta importada continua regra |
| ✓ | notas_web.py + templates/notas_etiqueta.html | dados_da_etiqueta / bloco .etiqueta | Notas | Etiqueta 100×30 (teor + fecho + selo + valores) | mistura + template | O texto impresso é a fórmula e o fecho (acima), lidos da base com o ajuste da casa. **O template fica**: é diagramação (`@page`, medidas da tela Ajustar etiqueta, o aviso de estouro em JS); a legenda do QR («confira o selo / selo.tjma.jus.br») é do endereço do QR, que de propósito não está no catálogo |
| ✓ | notas_livro.py | texto_termo_comparecimento | Notas | Termo de comparecimento («Saibam quantos este publico instrumento…») | f-string de frases (html) | **NOTAS_TERMO_COMPARECIMENTO** (+ peças `__documento`, `__selo`, `__documento_apresentado`, `__quem_assina`). O cabeçalho da serventia fica no código e entra no claro `{cabecalho}` (decisão do oficial de 07/09/2026). Sem acentos, como estava; regravado a cada reimpressão em `nt_presencas.conteudo`, como estava |
| ✓ | notas_livro.py | texto_termo_abertura / texto_termo_encerramento | Notas | Termos de abertura e encerramento do livro de notas | f-string de frases | **NOTAS_LIVRO_ABERTURA** e **NOTAS_LIVRO_ENCERRAMENTO** (+ peças `__usadas`, `__nenhuma`, `__termos`, `__inutilizadas`, `__motivo`). Congelados em `nt_livros` — o teste prova que o termo lavrado não muda. `escrituracao.texto_termo_abertura` (outra redação, das seis atribuições) não é das Notas e não foi tocado |
| ✓ | notas_livro.py | NOME_DA_SERIE | Notas | Nome da série no termo | constante | Peças `NOTAS_LIVRO_ABERTURA__serie_*`, lidas por `nome_da_serie`; o nome antigo responde. Sem acento e divergente de `TIPOS_LIVRO`, como estava. O termo segue o ajuste da casa; a DESCRIÇÃO gravada do livro (`nt_livros.descricao`, dado das listas e da importação) continua a de fábrica — se ela deve seguir o ajuste é pergunta para o oficial |
| ⊘ | notas_web.py | notas_livro_termo (moldura) | Notas | Cabeçalho da serventia + assinatura no .odt do termo | f-string html | **Fica no código.** O cabeçalho, pela decisão do oficial de 07/09/2026; o resto é a linha de assinatura com o nome e o título de quem responde — sem frase nenhuma. O texto do termo (acima) já está na base |
| ✓ | notas_inutilizacao.py | dizer / html_da_face | Notas | «INUTILIZAÇÃO. Fica(m) INUTILIZADA(S) a(s) face(s) … art. 795 §2º …» | mistura com regra | **NOTAS_INUTILIZACAO** (+ peças `__uma_face`, `__varias_faces`, `__razao_uma`, `__razao_varias`) e **NOTAS_INUTILIZACAO_FACE**; o traço (`{riscos}`) é regra e fica |
| ✓ | notas_anotacoes.py | _VERBO + texto_padrao | Notas | Anotação à margem («REVOGADA por ato lavrado nesta …») | mistura com regra | **NOTAS_ANOTACAO_MARGEM** (+ 19 peças: um verbo por tipo, a serventia de fora, o CNS, data, tipo, livro e folha, termo, ordem, selo). Congelada em `nt_ato_anotacoes`: `anotar` lê com a conexão, e a PRÓXIMA anotação segue o ajuste da casa; a já escrita não muda. Ajuste que não monta recusa a anotação — e o lançamento que a pediu volta junto |
| ✓ | notas_teor.py | ABERTURAS (+ UF_EXTENSO) | Notas | «SAIBAM quantos este público instrumento … virem que, aos …» | constante inteira (`str.format`) | **NOTAS_ABERTURA_ESCRITURA / _PROCURACAO / _SUBSTABELECIMENTO / _REVOGACAO / _ATA**. `UF_EXTENSO` fica: é o nome do estado com o artigo — dado, e não redação |
| ✓ | notas_teor.py | FECHOS | Notas | «E, de como assim o disse, do que dou fé…» | constante inteira | **NOTAS_FECHO_ESCRITURA / _PROCURACAO / _SUBSTABELECIMENTO / _REVOGACAO / _ATA**; o marcador `[ASSINANTES…]` continua trocado pela regra |
| ✓ | notas_teor.py | qualificar (+ _falta) | Notas | Qualificação art. 215 §1º CC | mistura com regra | **NOTAS_QUALIFICACAO_PF** e **NOTAS_QUALIFICACAO_PJ**. `_falta` fica: é o marcador do claro («[NACIONALIDADE]»), que a revisão tem de ver e que não pode ir ao livro |
| ✓ | notas_teor.py | _comparecimento_da_procuracao | Notas | «compareceu(ram) como OUTORGANTE(S) … nomeia e constitui …» | mistura com regra | Peças da abertura da procuração: `__um_outorgante`, `__varios_outorgantes`, `__um_procurador`, `__varios_procuradores`, `__na_qualidade` |
| ✓ | notas_teor.py | montar + _parte_com_rotulo / _qualificacao_no_lado | Notas | Corpo: «como VENDEDOR, …», «Presentes as testemunhas: …» | mistura com regra | Peças `NOTAS_ABERTURA_ESCRITURA__parte_com_papel`, `NOTAS_FECHO_ESCRITURA__testemunhas`, `NOTAS_QUALIFICACAO_PF__partes_do_testamento` |
| ✓ | notas_teor.py | texto_dos_assinantes / bloco_de_assinaturas | Notas | Assinantes e linhas de assinatura (`@@ASSINATURAS@@`) | f-string com regra | Peças `NOTAS_TRASLADO__assinatura`, `__assinatura_condicao` e `NOTAS_FECHO_ESCRITURA__testemunha` |
| ✓ | notas_teor.py | partes_por_lado, testemunhas_qualificadas, contexto_jinja_partes | Notas | `{{ outorgantes }}`, `{{ outorgados }}`, `{{ testemunhas }}` | mistura com regra | Sem texto próprio além de `qualificar` (na base) e do marcador `_falta`; passam `con` adiante |
| ✓ | notas_web.py | MODELO_TRASLADO_CABECALHO | Notas | Cabeçalho da página 2+ «LIVRO x / FOLHA n / TERMO» | template Jinja em constante | **NOTAS_TRASLADO_CABECALHO** (Jinja), o nome antigo responde |
| ✓ | notas_web.py | titulo_do_instrumento | Notas | Título do instrumento | mistura com regra | Peça `NOTAS_TRASLADO__titulo_da_escritura`; o resto é o nome do modelo ou `TIPOS_ATO` |
| ⊘ | notas_schema.py | TIPOS_ATO, TIPOS_LIVRO | Notas | Nomes de ato e de livro no papel | constante | **Fica no código.** É o vocabulário do sistema — telas, filtros, validação, CENSEC, ~20 módulos e templates —, e entra no papel como claro das peças (`{livro}`, `{tipo}`). Ler da base na hora do import em vinte lugares é o que o passo a passo proíbe. Continua divergindo de `NOME_DA_SERIE` |
| ✓ | notas_web.py | rótulo do selo (dicionário inline, 2×) | Notas | «SELO DA ESCRITURA / DA PROCURAÇÃO / …» | constante | Peças `NOTAS_TRASLADO__selo_*` (8) e **uma** função, `notas_web.rotulo_do_selo` — a duplicação acabou |
| ✓ | notas_web.py | notas_cartao_ficha → html_cab, selo de abertura | Notas | Cabeçalho do cartão de autógrafo; «SEM SELO DE ABERTURA. Anote o selo…» | f-string html | Peça `NOTAS_CARTAO_FICHA__sem_selo`. O cabeçalho fica fora do modelo por decisão do oficial (comentário no código) |
| ⊘ | notas_web.py | notas_ato_teor_odt → aviso | Notas | «RASCUNHO — ato N …» | f-string html | **Fica no código.** A importação do teor editado (`notas_ato_teor_importar`) reconhece o aviso pelo texto («RASCUNHO —», o nome da serventia, «Este documento é o teor em edição») para não trazê-lo para dentro do ato: editá-lo na base faria o aviso entrar no teor. Papel de conferência, que não sai da casa |
| ✓ | notas_certidao.py | NOME_DO_TIPO / frase_do_periodo | Notas | Título da certidão; «no período de … a …» / «em todo o acervo do sistema» | constante / regra | Peças `NOTAS_CERTIDAO_*__titulo` e `NOTAS_CERTIDAO_POSITIVA__periodo/__desde/__ate/__todo_o_acervo`; `NOME_DO_TIPO` responde pelo nome antigo (o padrão). A busca, a ficha e a moldura do .odt em `atribuicoes_web` leem com a conexão (`nome_do_tipo(con)`, `frase_do_periodo(…, con=con)`), como a certidão que `emitir` congela |

**E as minutas `nt_modelos`** (a seção «Fora deste inventário» acima): as 33
minutas de fábrica de `notas_modelos.py` foram para `modelos_padrao/notas/minutas/`
(o corpo, com os mesmos bytes, e o nome na ficha), carregadas na base. O ajuste
da casa continua em `nt_modelos`, como pedido; a subida (`instalar`) semeia a
linha de fábrica com o texto da base e não toca a editada. ✓

## LF06E — Protesto (23 linhas) — migrado ✓

> LF06E, 19/10/2026. Ouro gravado ANTES (commit 2c41e90) em
> `tests/fixtures/modelos_ouro/ouro_lf06e.py`: 120 saídas dos montadores puros,
> 6 que leem o banco e o retrato dos dicionários — tudo sai igual, byte a byte
> (`tests/test_modelos_da_casa.py`, bloco LF06E). A regra que escolhe a frase
> ficou no módulo; o texto foi para `modelos_padrao/protesto/`. **Cada peça é
> linha do catálogo, com ficha própria** (e não `<CHAVE>__<peca>`): a tela de
> Modelos, os elementos e a prévia põem a chave em maiúsculas, e a peça com
> nome em minúsculas ficaria lida e não editável. Os rótulos de dicionário
> viraram **peças-vocabulário** (`nome = texto`, uma linha cada — ver
> `protesto_pecas.vocabulario`): o nome é do sistema, o texto é do oficial.
> A tela confere cada peça ao gravar (`protesto_pecas.conferir`, a régua
> `conferir_claros` do LF06G com os claros do padrão; no vocabulário, linha por
> linha) — o claro que o papel não preencheria é recusado ali, e não no termo
> que se lavra.
> Três linhas ficaram no código de propósito (marcadas ⊘), com o porquê.
> **O termo lavrado no livro sai do PADRÃO das peças** (☐ nas três linhas do
> `protesto_termo.py`): o ajuste da casa delas vale na certidão e no
> instrumento, e o livro só o seguirá se o oficial decidir — mudar o que se
> lavra é regra de negócio (revisão do LF06E, 2ª volta).
> Legenda, a do LF06B: ✓ migrada · ⊘ fica no código, com o porquê · ☐ ficou
> para depois, com o motivo. 20 ✓ · 3 ⊘, e o ☐ do livro nas três linhas do termo.

| ✓ | módulo | função (ou constante) | atribuição | o que é | forma | observação |
|---|---|---|---|---|---|---|
| ✓ | protesto_certidao.py | montar_teor → pedido | Protesto | Abertura «a requerimento verbal / de FULANO / escrito do próprio devedor / por determinação judicial» | peças | **PT_CERTIDAO_PEDIDO_VERBAL**, **_REQUERENTE**, **_DEVEDOR**, **_JUDICIAL**. A regra (CN-MA arts. 944/948) escolhe; a vírgula antes do nome e os parênteses da ordem são juntura do código |
| ✓ | protesto_certidao.py | montar_teor → identificacao / inscrito | Protesto | «NOME CPF: x» (negativa) e « e inscrito no CPF: x» (positiva) | peças | **PT_CERTIDAO_IDENTIFICACAO**, **PT_CERTIDAO_INSCRITO**. As duas grafias continuam (o ouro as guarda); agora o oficial pode uni-las |
| ✓ | protesto_certidao.py | montar_teor → cabeca | Protesto | «CERTIFICO … revendo em meu Cartório, os livros … encontrei protesto contra …» | peça | **PT_CERTIDAO_CABECA**, editável. `PT_CERTIDAO_POSITIVA` continua «{cabeca} {corpo}» (o ajuste antigo segue montando); a declaração em `ESQUELETO_EM_VEZ_DE_TEXTO` diz onde o texto está |
| ✓ | protesto_certidao.py | montar_teor → fecho | Protesto | «CERTIFICO ainda que … consta a BAIXA e o CANCELAMENTO … art. 26 …» | peças | **PT_CERTIDAO_FECHO_UM**, **PT_CERTIDAO_FECHO_VARIOS**; a quantidade escolhe. O plural «as BAIXAS e o CANCELAMENTOS» ficou como estava (o ouro o guarda) — **o oficial o conserta na tela** (teste `test_o_fecho_que_o_oficial_corrige_na_tela_sai_na_certidao`) |
| ✓ | protesto_certidao.py | _linha_do_protesto | Protesto | Uma linha por protesto (título, espécie, protocolo, valores, apresentante, credor, livro/folha, EFEITOS SUSPENSOS, CANCELADO) | vocabulário | **PT_CERTIDAO_LINHA** — um pedaço por nome; o código escolhe quais entram e junta com «; ». A espécie continua em código cru («DMI»), como saía |
| ⊘ | protesto_certidao.py | MESES, _por_extenso_ano, _mes_e_ano | Protesto | Datas da certidão | regra | **Fica no código**: é a língua (nome do mês, número por extenso), e não frase da casa. `MESES` continua duplicado em `protesto_instrumento.MESES` |
| ✓ | protesto_termo.py | frase_do_edital | Protesto | «O devedor foi intimado por Edital em DD/MM/AAAA pelo motivo X.» | peças | **PT_TERMO_INTIMACAO_EDITAL**, **PT_TERMO_INTIMACAO_EDITAL_SEM_MOTIVO**. Congelado em `pt_atos.teor`. ☐ **O livro lavra o PADRÃO**: `protesto.lancar_protesto` chama `TERMO.montar` sem `con`, porque seguir o ajuste da casa muda o que se lavra (revisão do LF06E, 2ª volta) — pergunta ao oficial; se ele confirmar, é passar `con=con` |
| ✓ | protesto_termo.py | frase_da_intimacao_pessoal | Protesto | «intimado pessoalmente em …» / «por meio eletrônico …» | peças | **PT_TERMO_INTIMACAO_PESSOAL**, **PT_TERMO_INTIMACAO_DIGITAL**. ☐ O livro lavra o PADRÃO, como na linha acima |
| ✓ | protesto_termo.py | MOTIVO_NO_LIVRO, TIPO_NO_LIVRO | Protesto | «FALTA DE PAGAMENTO», «PARA FINS FALIMENTARES» → `{motivo}`/`{tipo}` | vocabulário | **PT_TERMO_MOTIVOS**, **PT_TERMO_TIPOS**. QUAIS códigos valem é regra (`MOTIVOS_DO_PROTESTO`, `TIPOS_DO_PROTESTO`): o ajuste não cria motivo. A certidão e o instrumento seguem o ajuste; ☐ no termo lavrado vale o PADRÃO, como nas frases acima. Continua duplicando `protesto_cra.MOTIVOS_DE_PROTESTO` com outra grafia |
| ✓ | protesto_instrumento.py | MENCAO_DA_COPIA_ARQUIVADA | Protesto | Menção do § único do art. 22 | peça | **PT_INSTRUMENTO_COPIA_ARQUIVADA** (o nome antigo responde pelo `__getattr__`). A cópia arquivada é perguntada ao banco, e escolhe |
| ✓ | protesto_instrumento.py | montar_teor → copia (sem cópia) | Protesto | «Não consta desta serventia cópia arquivada …» | peça | **PT_INSTRUMENTO_SEM_COPIA** |
| ✓ | protesto_instrumento.py | montar_teor → certidao (`{intimacao}`) | Protesto | Certidão do inciso IV (edital / entregue no endereço / não consta) | peças | **PT_INSTRUMENTO_INTIMACAO_EDITAL**, **_EDITAL_SEM_MOTIVO**, **_ENTREGUE**, **PT_INSTRUMENTO_SEM_INTIMACAO** e, desde o LD04 (21/10/2026), **PT_INSTRUMENTO_INTIMACAO_DIGITAL**: a digital caía em «entregue» e não batia com o termo — consertado |
| ✓ | protesto_instrumento.py | descricao_do_documento | Protesto | `{descricao}`: registro, protocolo, título, apresentante, credor, devedor, tipo e motivo | vocabulário | **PT_INSTRUMENTO_DESCRICAO**; a espécie por extenso vem de **PT_ESPECIES**. Desde o LD04 os pedaços (`pedacos_da_descricao`) servem também ao registro do protesto e ao termo do cancelamento |
| ✓ | protesto_termo.py | qualificacao + montar (LD04) | Protesto | A qualificação do registro no alto do termo (Lei 9.492, arts. 21, § 4º, e 22) | peça | **PT_TERMO_QUALIFICACAO** (novo, LD04). Vai também no termo que a casa personalizou. ☐ O livro lavra o PADRÃO, como as frases da intimação |
| ✓ | protesto_termo.py | montar_cancelamento (LD04) | Protesto | O termo do cancelamento (Lei 9.492, art. 26, § 6º), gravado em `pt_atos.teor` | papel | **PT_TERMO_CANCELAMENTO** (novo, LD04). O ajuste da casa chega pela rota, como o do termo do protesto |
| ✓ | protesto_livros.py | quitacao (LD04) | Protesto | A quitação do título pago no tabelionato (Lei 9.492, art. 19, § 2º; CN-MA art. 927) | papel | **PT_QUITACAO** (novo, LD04), e o título dela em **PT_MOLDURAS** (`quitacao_titulo`). Não congela: remonta-se do pagamento lançado |
| ✓ | protesto_certidao.py | paragrafo_do_protocolo (LD04) | Protesto | O Livro de Protocolo na certidão a pedido escrito do devedor ou por ordem judicial (CN-MA art. 906, § 2º) | vocabulário | **PT_CERTIDAO_LINHA** ganhou `protocolo_abertura`, `apontamento`, `titulo_apontado` e `ocorrencias` |
| ✓ | protesto.py | apresentante_do_titulo (LD08) | Protesto | O CPF/CNPJ e o endereço do apresentante, que a CRA não manda (CN-MA arts. 884, I, e 923; Lei 9.492, art. 22, II) | claro + vocabulário | **PT_AVISO_INTIMACAO** ganhou `{documento_do_apresentante}`; **PT_INSTRUMENTO_DESCRICAO** ganhou `apresentante_endereco` (o mesmo pedaço vai ao termo, `PT_TERMO_QUALIFICACAO`). A fonte é o título (balcão) ou o cadastro dos apresentantes (`pt_apresentantes.endereco`, novo) |
| ✓ | protesto_certidao.py | _linha_do_protesto (LD08) | Protesto | A data do protocolo e o tipo do endosso na linha da positiva (CNN art. 259, p. ú., V e VII) | vocabulário | **PT_CERTIDAO_LINHA** ganhou `protocolo_com_data`, `endosso`, `endosso_M` e `endosso_T` |
| ✓ | protesto_instrumento.py | emitir → praca | Protesto | «desta praça» quando falta a praça | peça | **PT_INSTRUMENTO_PRACA**. Continua afirmando praça sem dado — agora o oficial pode trocar a frase |
| ✓ | protesto_aviso.py | montar_teor_do_aviso | Protesto | Aviso de intimação inteiro | papel + vocabulário | **PT_AVISO_INTIMACAO** (papel novo do catálogo) e **PT_AVISO_ROTULOS** (documento, vencimento, aceite, «não informado»…). Não congela |
| ✓ | protesto_aviso.py | montar_teor_do_edital | Protesto | Edital de intimação inteiro | papel + vocabulário | **PT_EDITAL_INTIMACAO** e **PT_EDITAL_ROTULOS**. Congela em `pt_editais.teor` + hash: o já publicado não muda. A linha do prazo-limite sai em branco sem prazo (regra do código). «Protocolo: A CONFERIR» continua indo ao papel |
| ✓ | protesto_aviso.py | canhoto_do_aviso | Protesto | Canhoto «COMPROVANTE DE RECEBIMENTO DA INTIMAÇÃO» | peças | **PT_AVISO_CANHOTO_TITULO**, **_IDENTIFICACAO**, **_CAMPOS**, **_TENTATIVAS_TITULO**, **_TENTATIVA** (uma linha do papel por linha da peça). A moldura continua em `atribuicoes_web.py` |
| ⊘ | protesto_aviso.py | MOTIVOS_NAO_ENTREGA, MOTIVOS_INATIVOS, motivo_rotulo | Protesto | Rótulos de não-entrega | catálogo com regra | **Fica no código**: é o catálogo do E-Ofício (`tbMotivoNEntrega`) transcrito, com as marcas que são regra (`edital`, `contador`, `usos`). O rótulo vai à tela, ao comprovante interno e ao XML da CENPROT — nenhum papel desta casa o imprime (o «pelo motivo X» do termo vem do `detalhe_json` do ato) |
| ✓ | protesto_livros.py | FORMAS + livro_de_pagamentos | Protesto | Coluna «ocorrências» do Livro de Pagamentos | vocabulário | **PT_LIVRO_PAGAMENTOS**. QUAIS formas valem é `protesto.FORMAS_DE_PAGAMENTO` (a duplicata `FORMAS` saiu do código) |
| ✓ | protesto_livros.py | OCORRENCIA_DO_ATO + livro_de_protocolo | Protesto | Ocorrências do Livro de Protocolo | vocabulário | **PT_LIVRO_PROTOCOLO**; os atos que entram são `ATOS_NO_PROTOCOLO`. A intimação digital continua saindo «intimado pessoalmente» — achado mantido |
| ⊘ | protesto.py | CATALOGO_CANCELAMENTO | Protesto | Rótulo e fundamento legal de cada hipótese de cancelamento | catálogo com regra | **Fica no código**: é a lista das hipóteses (regra — `cancelar` recusa a que não está nela), e não chega ao papel: vai à tela e ao `detalhe_json`. Se um dia for ao papel, vira peça |
| ✓ | protesto_cra.py | ESPECIES | Protesto | Nome por extenso da espécie (aviso, canhoto, instrumento, livros) | vocabulário | **PT_ESPECIES** — o nome NO PAPEL, nascido igual à glosa. `protesto_cra.ESPECIES` (a glosa do leiaute) continua no código, que confere a remessa com ela |
| ✓ | atribuicoes_web.py | protesto_certidao_odt / protesto_livro / protesto_aviso_odt / protesto_editais_do_dia_odt / protesto_instrumento_odt | Protesto | Molduras dos papéis do protesto (título «CERTIDÃO {tipo} DE PROTESTO», «Autenticidade: hash»…) | vocabulário | **PT_MOLDURAS**: título e número da certidão e do instrumento, «CERTIDÃO CANCELADA», local e data, o rodapé de autenticidade, o «DESTAQUE AQUI» do canhoto, o separador da folha de editais, título, artigo e colunas dos dois livros. O HTML (alinhamento, tabela) e QUAIS colunas ficam no código; o cabeçalho da casa e a assinatura não entraram (decisão do oficial de 07/09/2026). Ouro do HTML das 8 rotas em `LF06E_molduras.json` |

## LF06F — RTD/RCPJ e Caixa (inclui WhatsApp ao cliente) (22 linhas)

> **LF06F, 19/10/2026:** ✓ migrada (a chave está na observação) · ☐ ficou para depois, com o
> motivo. Sete papéis novos no catálogo (`modelos_papeis/rcpj_rtd.py` e `caixa.py`, grupo
> LF06F) e doze peças; o ouro está em `tests/fixtures/modelos_ouro/ouro_lf06f.py`
> (`LF06F_papeis.json`, árvore de 2c41e90, 82 montadores e 16 telas). 20 ✓ · 2 ☐ (o
> lançamento no livro, que é pergunta à casa, e a frase do cancelado no Livro 3).

| ☐ | módulo | função (ou constante) | atribuição | o que é | forma | observação |
|---|---|---|---|---|---|---|
| ✓ | atrib_certidao.py | MODELO_CERTIDAO_RCPJ_RTD_SO_AVERBACOES | RCPJ e RTD | Abertura da certidão de inteiro teor quando só se certificam averbações | constante inteira | Regra (`eh_so_averbacoes`) decide; `montar_teor` ignora o catálogo de propósito — falta chave própria. Congelado em `at_certidoes.teor` (sha256) — ✓ LF06F: papel **RCPJ_RTD_CERTIDAO_SO_AVERBACOES** (chave própria; `emitir` busca o ajuste da casa) |
| ✓ | atrib_certidao.py | montar_teor (claro `{onde}`) + NOME_DO_REGISTRO | RCPJ e RTD | «no Livro "A-5" de Registro de Pessoas Jurídicas, fls. X, ATO n. N datada de …» | f-string de frases | Congelado. Nome do livro diverge de `rg_certidao_pdf.livro_impresso` (duplicado) — ✓ LF06F: peças **RCPJ_CERTIDAO__onde**, `__onde_folha`, `__onde_ato`, `__onde_data`, `__registro_rcpj`, `__registro_rtd`, `__registro`; a regra (`PECA_DO_REGISTRO`, folha/número/data presentes) ficou em `montar_teor` |
| ✓ | atrib_certidao.py | montar_teor (bloco de averbação) | RCPJ e RTD | Separador «--- AVERBAÇÃO n. X ---» + teor de cada averbação | f-string | Regra decide quais entram (`ato_ids`). Congelado — ✓ LF06F: peça **RCPJ_CERTIDAO__averbacao** |
| ☐ | atrib_certidao.py | emitir / remontar_teor_certidao_livro3 | RCPJ e RTD; RI Livro 3 | «CERTIFICO ainda que o referido registro encontra-se CANCELADO nesta Serventia.» | literal por regra | Duas cópias; `blocos_por_ato` procura a frase literal. Congelado — lote: LF06F (RCPJ/RTD) · LF06B (Livro 3) — ✓ LF06F só RCPJ/RTD: peça **RCPJ_CERTIDAO__cancelado** em `emitir`. ☐ Livro 3 (`emitir` e `remontar_teor_certidao_livro3`): o LF06B, já integrado, não a levou, e ela continua literal — `remontar_teor_certidao_livro3` confere «CANCELADO nesta Serventia» no teor para não repetir a frase, e uma frase editada a faria sair duas vezes; levar junto com essa conferência |
| ✓ | rg_teor_rtdpj.py | intro | RCPJ e RTD | «CERTIFICO que me foi apresentado para ser AVERBADO/REGISTRADO no Registro nº …» | f-string de frases | Duplica a seção `===INTRO===` do papel do catálogo; alternativa quando o modelo perde a marca e em `teor_texto_curto` — ✓ LF06F: lê a ===INTRO=== do PADRÃO do papel `*_TEOR_*` (os mesmos bytes da f-string, para qualquer valor digitado); sem cópia no código. O ajuste da casa não entra aqui — ver a linha de baixo |
| ☐ | atribuicoes_web.py | rcpj_rtd_lancar | RCPJ e RTD | Teor da averbação gravado no livro (`rg_atos.teor`) com `RGTEOR.intro(...)` | mistura com regra | Congelado no livro. Não segue o catálogo `*_TEOR_AVERBACAO`: editar o modelo muda o PDF e não o livro — ☐ LF06F, para a casa decidir: o texto saiu do código (é a ===INTRO=== do padrão, pela `intro` da linha de cima), mas o livro continua sem seguir o ajuste da casa, como antes. A primeira volta do LF06F fez o lançamento seguir a intro ajustada, e a revisão apontou que isso muda o que se lavra — regra da casa, e não migração do texto. Se o oficial quiser, é passar a série e o `con` à `intro` e ler as seções do ajuste da casa no lugar de `secoes_do_padrao` (foi o que a primeira volta fez, no commit `fb33694`, que ficou fora de ramo: o `refazer/LF06F` guarda a segunda volta, que já não segue o ajuste) |
| ✓ | rg_teor_rtdpj.py | encerramento | RCPJ e RTD | «Era o que continha o documento apresentado para … Eu, X, função, o subscrevo e assino.» | f-string | Duplica `===ENCERRAMENTO===`; alternativa — ✓ LF06F: a ===ENCERRAMENTO=== do padrão do papel |
| ✓ | rg_teor_rtdpj.py | linhas_cabecalho | RCPJ e RTD | «{unidade} — CNS {cns}» + atribuição | f-string | Duplica `===CABECALHO===`; alternativa — ✓ LF06F: a ===CABECALHO=== do padrão do papel |
| ✓ | rg_teor_rtdpj.py | linha_data / data_por_extenso | RCPJ e RTD | «{cidade}/{uf}, {data por extenso}.» | f-string | Duplica `===DATA===` e `ri_web.data_por_extenso` — ✓ LF06F: `linha_data` é a ===DATA=== do padrão. `data_por_extenso` fica: é a data por extenso (os meses), e não frase de papel; a duplicata com `ri_web.data_por_extenso` continua |
| ✓ | rg_teor_rtdpj.py | _desenhar_encerramento | RCPJ e RTD | Linha de assinatura «{função}: ________» | f-string | Sai fora do modelo — ✓ LF06F: papel **RCPJ_RTD_PDF_MOLDURA**, parte ===ASSINATURA=== |
| ✓ | rg_teor_rtdpj.py | SELO_FAIXA_ROTULO(_ARQUIVAMENTO), _carimbo_do_selo | RCPJ e RTD | «selo averbação» / «selo arquivamento», «Consulte em {endereço}» | constante + f-string | Regra decide a 2ª caixa (15.22) — ✓ LF06F: RCPJ_RTD_PDF_MOLDURA ===SELO_AVERBACAO===, ===SELO_ARQUIVAMENTO===, ===SELO_CONSULTE=== (os nomes antigos respondem pelo `__getattr__`) |
| ✓ | rg_certidao_pdf.py | contexto_certidao (valores padrão) | RCPJ e RTD | «o registro de {natureza}», «Registro Nº {n}» | f-string | Prévia e via final divergem nas certidões só de averbações — ✓ LF06F: RCPJ_RTD_PDF_MOLDURA ===OBJETO===, ===OBJETO_SEM_NATUREZA===, ===IDENTIFICACAO===. A divergência prévia × via final continua |
| ✓ | rg_certidao_pdf.py | livro_impresso | RCPJ e RTD | «Livro de Registro de Títulos e Documentos B-5» (claro `{livro}`) | f-string | Duplicado de `atrib_certidao._livro_impresso`, com padrão diferente («A» × «?») — ✓ LF06F: RCPJ_RTD_PDF_MOLDURA ===LIVRO_RCPJ=== / ===LIVRO_RTD===. A diferença de padrão com `atrib_certidao._livro_impresso` («A» × «?») continua |
| ✓ | rg_certidao_pdf.py | montar_folha_interna, _desenhar_area_selo, CAMPOS_EMOL | RCPJ e RTD | «Página 000001/0000NN», molduras de selo/QR, quadro FERC/FADEP/FEMP/FERRFIS | literais no desenho | Quadro ligado por padrão — ✓ LF06F: «Página», «selo da certidão», «selo / verificação», «QR / autenticação» na RCPJ_RTD_PDF_MOLDURA. `CAMPOS_EMOL` fica no código: são os nomes dos fundos (`custas`, `atribuicoes.FUNDOS`), e não frase — duas fontes para o nome de um fundo divergiriam |
| ✓ | atribuicoes_web.py | atribuicoes_certidao_imprimir | RCPJ e RTD | Objeto certificado «a(s) averbação(ões) nº X (natureza), …» | mistura com regra | Não congelado: refeito a cada impressão com o usuário logado e a data de hoje — ✓ LF06F: RCPJ_RTD_PDF_MOLDURA ===OBJETO_AVERBACOES===, ===AVERBACAO_COM_NATUREZA===, ===AVERBACAO_SEM_NATUREZA===, ===IDENTIFICACAO_AVERBACAO(ES)=== |
| ✓ | atribuicoes_web.py | atribuicoes_certidao_odt (RCPJ/RTD por texto) | RCPJ e RTD | ODT: cabeçalho, «CERTIDÃO n.», «CERTIDÃO CANCELADA — motivo», local/data, assinatura, «Autenticidade: hash» | f-string HTML | Data de hoje e titular atual, não quem emitiu — ✓ LF06F: papel **RCPJ_RTD_CERTIDAO_ODT** (`atrib_certidao.papel_por_texto`). Data de hoje e titular atual continuam |
| ✓ | rg_web.py + templates/rcpj_rtd_nota.html | rcpj_rtd_titulo_nota | RCPJ e RTD | Nota devolutiva: «Pelo presente, comunico ao apresentante…», EXIGÊNCIAS, FUNDAMENTO, prazo | template HTML | Regra decide o prazo. Não congelada. O RI tem `RI_NOTA` no catálogo, esta não — ✓ LF06F: papel **RCPJ_RTD_NOTA** (o template ficou com a página) |
| ✓ | rg_web.py + templates/rcpj_rtd_etiqueta.html | rcpj_rtd_etiqueta | RCPJ e RTD | Etiqueta do título: «{Tipo} — Livro …, fl. …, sob o n. …», selo | template HTML | Registro cancelado bloqueia — ✓ LF06F: papel **RCPJ_RTD_ETIQUETA** (o template ficou com a página) |
| ✓ | rg_web.py + templates/rcpj_rtd_etiquetas_selos_externos_imprimir.html | rcpj_rtd_etiquetas_selos_externos | RCPJ e RTD | «RCPJ E RTD — REGISTRO/AVERBAÇÃO», «— SELO ELETRÔNICO» | constante + template | — — ✓ LF06F: papel **RCPJ_RTD_ETIQUETA_SELO_EXTERNO**, título em peças `__manual` / `__razao` |
| ✓ | caixa_schema.py | AVISO_ORCAMENTO | Caixa | «Este documento corresponde a MERO CÁLCULO DE EMOLUMENTOS…» | constante inteira | Entra no `CAIXA_ORCAMENTO` via `{{ aviso }}`; o molde está no catálogo, o aviso (afirmação jurídica) não — ✓ LF06F: peça **CAIXA_ORCAMENTO__aviso** (o nome antigo responde pelo `__getattr__` de `caixa_schema`) |
| ✓ | wa_textos.py | bloco_contato (+ endereco_da_casa) | Caixa (WhatsApp) | Assinatura «{nome}, Oficio unico de {cidade}. Telefone … E-mail …» | f-string | Sem acentos; em todos os rascunhos — ✓ LF06F: papel **CAIXA_WHATSAPP**, ===CONTATO=== e ===ENDERECO_DA_CASA=== |
| ✓ | wa_textos.py | rascunho_horario / _endereco / _documentos / _certidao / _firma / _protesto / _outros | Caixa (WhatsApp) | Rascunhos de resposta ao cliente | f-string de frases | Regra (`wa_balcao.classificar`) decide qual; gravado em `wa_mensagem` ao enviar — ✓ LF06F: papel **CAIXA_WHATSAPP**, uma parte por assunto; o ajuste torto sai como o padrão, para a mensagem que chegou não se perder |

## LF06G — Retificação, Usucapião, Resolve e o resto (selo no papel, comuns) (15 linhas)

> **LF06G, 19/10/2026.** Doze linhas migradas (✓), três decididas «fica no
> código» (—), cada uma com o motivo. Os papéis da retificação e da usucapião
> são do **Registro de Imóveis** (procedimentos do oficial de RI, e não
> atribuições): pastas `modelos_padrao/retificacao/` e
> `modelos_padrao/usucapiao/`, nove papéis no catálogo, 41 peças. Ouro em
> `tests/fixtures/modelos_ouro/ouro_lf06g.py` (commit 2c41e90, 30 saídas).
> Conferidos o Resolve (`resolve_intimacao`, `resolve_api`, `resolve_web`) e a
> CENPROT/centrais: só montam o JSON da Central e mensagens de tela — nenhum
> texto de papel desta casa (ver «Fora deste inventário»).

| ☐ | módulo | função (ou constante) | atribuição | o que é | forma | observação |
|---|---|---|---|---|---|---|
| ✓ | usucapiao.py | montar_dossie | Usucapião | Dossiê enviado a terceiros | f-string de frases | Relatório, não papel assinado. **O pedido a quem analisa → `US_DOSSIE_PEDIDO`** (texto da casa, editável). O resto é o processo listado (dados, regra de máscara) e fica no código |
| ✓ | rt_notificacao.py | MODELO | Retificação | Notificação ao confrontante, com RECIBO destacável | constante inteira | **`RT_NOTIFICACAO_CONFRONTANTE`**, bytes iguais. Congelada em `rt_confrontantes.teor_expedido` (o ajuste vale para a próxima); frase da impugnação atrasada reescreve `rt_tjma.IMPUGNACAO_ATRASADA_ENTRA` |
| ✓ | rt_notificacao.py | montar (+ _quem_faz_a_divisa, _documento) | Retificação | «Divisa que toca o imóvel de V. S.ª…», prazo «15 (quinze) dias úteis» | mistura com regra | Peças **`RT_NOTIFICACAO_CONFRONTANTE__divisa`, `__divisa_matricula`, `__divisa_matricula_serventia`, `__contigua`, `__sem_descricao`, `__imovel_matricula`/`_area_na_matricula`/`_area_pretendida`/`_perimetro`, `__planta`, `__planta_credencial`, `__planta_art`, `__prazo_uteis`, `__prazo_corridos`, `__sobre_matricula`**. Regra (art. 596, 599) no código. `_documento` fica: «CPF»/«CNPJ»/«documento» é o tipo do número, medido pelo tamanho |
| ✓ | rt_tjma.py | SILENCIO_VALE_ANUENCIA | Retificação | «Será presumida a anuência do confrontante…» | constante inteira | Peça **`RT_NOTIFICACAO_CONFRONTANTE__silencio`** (a frase do papel). A norma continua em `rt_tjma` (tela das normas); teste confere que o padrão da peça parte dela |
| ✓ | rt_tjma.py | COMO_NOTIFICAR (o_que) | Retificação / Usucapião | «Pessoalmente…», «Correio com aviso de recebimento» | constante | Peças **`US_NOTIFICACAO__forma_pessoal`, `__forma_rtd`, `__forma_correio`, `__forma_edital`** (o recibo). A lista, a ordem e o artigo seguem na norma; na retificação a forma não vai ao papel |
| — | retificacao_web.py / usucapiao_web.py | _hoje_extenso | Retificação / Usucapião | Fecho «Cidade-UF, 21 de setembro de 2026» | f-string | **Fica no código (LF06G)**: não há frase — é o lugar do cadastro e a data de `ri_web.data_por_extenso` (LF06B), juntos por vírgula. As duas montagens dão o mesmo texto e diferem no RELÓGIO (`db.now()` na retificação, `date.today()` na usucapião): achado, não modelo |
| ✓ | us_notificacao.py | CABECA + CORPO | Usucapião | Notificação de usucapião extrajudicial com RECIBO | constante inteira | **`US_NOTIFICACAO`** (o corpo, bytes iguais) e **`US_NOTIFICACAO__cabeca`**. Congelada em `us_movimentos.teor_expedido` |
| ✓ | us_notificacao.py | montar | Usucapião | «O requerente alega posse…», «DECORRIDO O PRAZO SEM MANIFESTAÇÃO, O SILÊNCIO…» | mistura com regra | Peças **`US_NOTIFICACAO__posse`, `__posse_desde`, `__silencio`, `__imovel_situado_em`, `__imovel_municipio`, `__imovel_municipio_uf`, `__imovel_area`, `__prazo_uteis`, `__prazo_corridos`**. `SILENCIO_CONCORDA` continua sendo a norma da tela. Congelado |
| ✓ | us_notificacao.py | EDITAL | Usucapião | Edital de usucapião («FAZ SABER a quantos este edital virem…») | constante inteira | **`US_EDITAL`**, bytes iguais. Congelado |
| ✓ | us_notificacao.py | montar_edital | Usucapião | «CONSIGNA-SE EXPRESSAMENTE que o imóvel não tem origem registrária…» | mistura com regra | Peças **`US_EDITAL__sem_origem`** (regra do art. 755 §2º no código), **`__posse`, `__imovel_situado_em`, `__imovel_municipio`, `__imovel_area`, `__prazo`**. Congelado |
| ✓ | us_notificacao.py | OFICIO_AO_ENTE | Usucapião | Ofício à União/Estado/Município («Comunico a V. Sa.…») | constante inteira | **`US_OFICIO_AO_ENTE`**, bytes iguais. Congelado |
| ✓ | us_notificacao.py | montar_oficio_ao_ente | Usucapião | Bloco do imóvel, posse e prazo do ofício | f-string | Peças **`US_OFICIO_AO_ENTE__posse`, `__imovel_situado_em`, `__imovel_municipio`, `__imovel_area`, `__prazo`**. O bloco do imóvel virou uma regra só com o edital (`_linhas_do_imovel`); o texto de cada linha é de cada papel. `_por_extenso` fica (formata número) |
| ✓ | usucapiao.py | modelos_de_decisao | Usucapião | Decisão PROCEDENTE / IMPROCEDENTE / NOTA DE EXIGÊNCIA / REMESSA AO JUÍZO + fecho | f-string de frases | **`US_DECISAO_PROCEDENTE`, `US_DECISAO_IMPROCEDENTE`, `US_DECISAO_EXIGENCIA`, `US_DECISAO_REMESSA_JUIZO`**, com o fecho dentro de cada. Regra (sentido) no código; a ficha do processo oferece o ajuste da casa. Congelado em `us_decisoes.teor` |
| — | selo_no_papel.py | ROTULO_NO_PAPEL + linha_de_valores | Todas | «Total R$ … Emol R$ … FERC R$ …» | mistura com regra | **Fica no código (LF06G)**: é o que o SELO declara, na forma do aparelho do TJMA (medido em 25.634 selos) — o `ROTULO_NO_PAPEL` existe para o papel escrever a palavra do selo. Editável, o papel deixaria de reproduzir o selo que certifica |
| — | selo_no_papel.py | detalhe, marcas, requerente, linhas_do_carimbo, ato_e_data, valores_com_marcas | Todas | Linhas do carimbo do selo | mistura com regra | **Fica no código (LF06G)**: quem chama são os desenhos de cinco atribuições (`ri_odt`, `rc_certidao_odt`, `rg_teor_rtdpj`, notas, `atribuicoes_web`), todos sem conexão — uma peça ali seria lida só do padrão, e o ajuste da casa nunca chegaria; e «Todas» não é atribuição com tela. As frases da casa («emitida em … às …», «Requerente:») ficam como pergunta ao oficial |

---

**199 linhas** a migrar, de LF06B a LF06G. Ao migrar, troque ☐ por ✓ e diga na observação a `<CHAVE>` que o papel ganhou.

LF06C (19/10/2026): as 73 linhas do Registro Civil estão decididas — ✓ ou ⊘
na seção dele, com o papel, as peças ou a razão de ficar no código.

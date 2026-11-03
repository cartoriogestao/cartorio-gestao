# Inventário dos atos — Tabelionato de Notas

Pedido do oficial (01/11/2026): o «ensaio de atos», um teste que pratique todos os atos previstos em lei
e nos códigos de normas e confira a saída. Este é o inventário das Notas, a segunda atribuição, depois do
RCPN (`inventario_rcpn.md`). Para cada ato e cada papel, a norma, se o sistema tem tela, e o que já o
pratica.

**As fontes.** Os requisitos elemento a elemento, com o artigo, já estão em `docs/REQUISITOS_LEGAIS.md`,
seção «Tabelionato de Notas (LT02)», e são conferidos pela matriz de `tests/test_requisitos_notas.py`:
este inventário não os repete, aponta para lá, e cita só o artigo próprio de cada ato. Os artigos do CNN
(Prov. CNJ 149/2023) e do CN-MA (Prov. COGEX 28/2026) são os que aquele documento já citou a partir dos
textos de `migracao-pg/referencia/`. **Esses textos não estão nesta máquina**: o que este inventário
acrescenta cita só o Código Civil, as leis federais e os provimentos do CNJ pelo número, e o artigo do
CNN ou do CN-MA que precisaria do texto está marcado «conferir». A lei de emolumentos do Maranhão não foi
conferida nesta rodada (o item da tabela é o que `tests/test_fluxo_notas.py` já cobra).

**O que já pratica as Notas.** Ao contrário do RCPN, as Notas já tinham um ensaio de ponta a ponta antes
deste pedido: `tests/test_fluxo_notas.py` leva **cada minuta de fábrica** do protocolo pago à certidão,
pelas telas (`test_o_ato_de_livro_vai_do_protocolo_a_certidao_fiel_ao_termo`), e
`test_cada_minuta_de_fabrica_tem_o_seu_caso_ponta_a_ponta` falha se nascer minuta sem caso. Mas cada caso
é **um só**: duas pessoas solteiras, maiores, que assinam, sem procurador. O ensaio desta rodada varia
**as partes e as situações** que mudam o texto ou travam a lavratura — e é aí que está a coluna «Ensaio».

**Legenda.** Tela: ✓ tem · parcial (há tela, falta campo que a lei pede) · ✗ não tem.
Ensaio: fluxo (um caso em `test_fluxo_notas.py`) · matriz (o modelo em `test_requisitos_notas.py`) ·
**plano**: o que esta rodada vai praticar · — nada.

## Situações das partes (valem para todo ato de livro)

O que o CN-MA art. 798 pede conforme quem comparece, e que muda o texto de qualquer escritura, procuração
ou ata. É o centro do ensaio desta rodada.

| Situação | Norma | Tela | Ensaio |
|---|---|---|---|
| Parte casada: cônjuge e regime de bens na qualificação | CC art. 215, § 1º, III; CN-MA art. 798, V | ✓ (LD07: `qualificacao_civil`) | matriz · **plano**: casado em comunhão parcial vendendo imóvel |
| Outorga do cônjuge para alienar ou gravar imóvel | CC art. 1.647, I | parcial — o cônjuge entra como parte, sem a qualidade de anuente | **plano** |
| Parte em união estável | CNN art. 111; CN-MA art. 798, V | ✓ | **plano** |
| Parte representada por procurador: livro, folha e serventia da procuração | CN-MA art. 798, VI | parcial — sem campo; só no texto livre | **plano** |
| Menor ou incapaz: nascimento com livro, folha e termo, e quem assiste ou representa | CN-MA art. 798, VII | parcial — sem campo; só no texto livre | **plano** |
| Pessoa jurídica, com quem a representa e o ato constitutivo | CN-MA art. 798, V (modelo NOTAS_QUALIFICACAO_PJ) | ✓ | matriz · **plano** |
| Comparecente que não é conhecido nem tem documento: duas testemunhas de conhecimento | CC art. 215, § 5º; CN-MA art. 798, III | parcial — testemunha comum | **plano** |
| Quem não sabe ou não pode assinar: assinatura a rogo e impressão digital | CC art. 215, § 2º | parcial — a qualidade «assina a rogo» existe (`notas_web`); o texto não | **plano** |
| Estrangeiro que não entende o idioma: tradutor público ou intérprete | CC art. 215, § 4º | ✗ | **plano** (texto) |
| Estrangeiro: país de nascimento e de residência para a CENSEC e a DOI | CNN (conferir o artigo) | ✓ (colunas `pais_*` de `nt_ato_partes`) | **plano** |
| Cego, surdo, surdo-mudo no testamento | CC arts. 1.866, 1.867 e 1.873 | ✗ — só nos requisitos da minuta | **plano** |

## Escrituras

| Ato | Norma própria | Tela | Ensaio |
|---|---|---|---|
| Compra e venda de imóvel urbano | LRP arts. 222 e 225; CN-MA art. 800 | ✓ minuta NT-ESC-COMPRA-VENDA | fluxo, matriz · **plano**: casado, por procurador, PJ compradora |
| Compra e venda de imóvel rural | LRP arts. 222 e 225; CN-MA arts. 800, 801, V, e 802, § 5º | ✓ NT-ESC-COMPRA-VENDA-RURAL | fluxo, matriz · **plano**: estrangeiro comprador (conferir a Lei 5.709/1971) |
| Doação (com ou sem reserva de usufruto) | CC art. 539; CN-MA art. 800 | ✓ NT-ESC-DOACAO | fluxo, matriz · **plano**: doação a menor, aceita pelo representante |
| Hipoteca | CC arts. 1.424 e 1.647, I | ✓ NT-ESC-HIPOTECA | fluxo, matriz |
| Alienação fiduciária de imóvel | Lei 9.514/1997, art. 24 | ✓ NT-ESC-ALIENACAO-FIDUCIARIA | fluxo, matriz · **plano**: credor PJ |
| Confissão de dívida e dação em pagamento | CC arts. 356 e 357 | ✓ NT-ESC-CONFISSAO-DACAO | fluxo, matriz |
| Permuta | CC art. 533 | ✓ NT-ESC-PERMUTA | fluxo, matriz |
| Usufruto (instituição, renúncia, extinção) | CC arts. 1.390 e 1.410 | ✓ NT-ESC-USUFRUTO | fluxo, matriz |
| Cessão de direitos hereditários | CN-MA arts. 799, VIII, 803 a 805 | ✓ NT-ESC-CESSAO-HEREDITARIA | fluxo, matriz · **plano**: cedente casado (outorga) |
| Inventário e partilha | CNN art. 441; CN-MA arts. 808 a 822 | ✓ NT-ESC-INVENTARIO-PARTILHA | fluxo, matriz · **plano**: viúvo meeiro e dois herdeiros, um casado; advogado |
| Sobrepartilha | CN-MA arts. 813 e 817 | ✓ NT-ESC-SOBREPARTILHA | fluxo, matriz |
| Partilha ou adjudicação (herdeiro único) | CN-MA art. 814 | ✓ NT-ESC-PARTILHA-ADJUDICACAO | fluxo, matriz · **plano**: herdeiro único |
| Nomeação de inventariante | CN-MA art. 810 | ✓ NT-ESC-NOMEACAO-INVENTARIANTE | fluxo, matriz |
| Divórcio consensual | CN-MA arts. 821, 822, 824 e 826 | ✓ NT-ESC-DIVORCIO | fluxo, matriz · **plano**: com partilha, com volta ao nome de solteira |
| Separação consensual | CN-MA arts. 822 e 823 | ✓ NT-ESC-SEPARACAO | fluxo, matriz |
| Conversão da separação em divórcio | CN-MA art. 830 | ✓ NT-ESC-CONVERSAO-DIVORCIO | fluxo, matriz |
| Restabelecimento da sociedade conjugal | CN-MA arts. 828 e 829 | ✓ NT-ESC-RESTABELECIMENTO | fluxo, matriz |
| Declaratória de união estável | CC arts. 1.723 e 1.725; CNN art. 537, § 4º | ✓ NT-ESC-UNIAO-ESTAVEL | fluxo, matriz · **plano**: com regime diverso da comunhão parcial |
| Dissolução de união estável | CNN art. 537, § 4º; CN-MA art. 822 | ✓ NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL | fluxo, matriz |
| Emancipação | CC art. 5º, par. ún., I; LRP art. 90 | ✓ NT-ESC-EMANCIPACAO | fluxo, matriz · **plano**: só a mãe, pai falecido |
| Pacto antenupcial | CC arts. 1.653 e 1.657; LRP art. 244 | ✓ NT-ESC-PACTO-ANTENUPCIAL | fluxo, matriz · **plano**: nubente menor, com o assistente (CC art. 1.654) |
| Quitação | CC art. 320 | ✓ NT-ESC-QUITACAO | fluxo, matriz |
| Distrato | CC art. 472 | ✓ NT-ESC-DISTRATO | fluxo, matriz |
| Diretivas antecipadas de vontade | CN-MA arts. 876 e 877 | ✓ NT-ESC-DIRETIVAS-VONTADE | fluxo, matriz |
| Renúncia (abdicação) de herança | CC art. 1.806 | ✗ — não há minuta | — |
| Reconhecimento de filho | CC art. 1.609, II; Lei 8.560/1992, art. 1º, II | ✗ — não há minuta | — |
| Instituição de bem de família | CC art. 1.711 | ✗ — não há minuta | — |
| Divisão e extinção de condomínio | CC art. 1.320 | ✗ — não há minuta | — |
| Instituição de servidão | CC art. 1.378 | ✗ — não há minuta | — |

## Procurações e mandato

| Ato | Norma própria | Tela | Ensaio |
|---|---|---|---|
| Procuração pública | CC arts. 654, § 1º, e 661, § 1º; CN-MA art. 833 | ✓ NT-PROC-PUBLICA | fluxo, matriz · **plano**: poderes para alienar imóvel (certidão do RI, CN-MA art. 833); outorgante a rogo |
| Procuração em causa própria | CC art. 685; CN-MA art. 835 | ✓ NT-PROC-CAUSA-PROPRIA | fluxo, matriz |
| Procuração para fins previdenciários (isenta) | Lei 8.213/1991, art. 109 | ✓ NT-PROC-PREVIDENCIARIA | fluxo, matriz |
| Substabelecimento | CC art. 667; CN-MA arts. 789 e 831 | ✓ NT-SUBSTABELECIMENTO | fluxo, matriz · **plano**: de procuração de outra serventia |
| Revogação de mandato (e a anotação na procuração) | CN-MA art. 831 | ✓ NT-REVOGACAO-MANDATO; anotação em `/notas/anotacoes/pendentes` | fluxo, matriz · **plano**: revoga procuração desta serventia e a margem a anota |
| Renúncia de mandato | CN-MA art. 831, § 4º | ✓ NT-RENUNCIA-MANDATO | fluxo, matriz |

## Testamentos

| Ato | Norma própria | Tela | Ensaio |
|---|---|---|---|
| Testamento público | CC arts. 1.857, 1.860 e 1.864 a 1.867 | ✓ NT-TESTAMENTO-PUBLICO | fluxo, matriz · **plano**: testador que não sabe assinar (CC art. 1.865); testador cego (CC art. 1.867) |
| Testamento cerrado — auto de aprovação | CC arts. 1.868 a 1.875 | ✓ NT-TESTAMENTO-CERRADO | fluxo, matriz |
| Revogação de testamento | CC arts. 1.969 a 1.972 | parcial — sem minuta própria; pelo testamento público | — |
| Comunicação ao RCTO da CENSEC | CN-MA art. 785, I | ✓ `/notas/remessas` | `tests/test_notas_censec.py` · **plano**: o testamento entra na remessa, e não na CEP |

## Atas notariais

| Ato | Norma própria | Tela | Ensaio |
|---|---|---|---|
| Ata notarial | CC art. 1.864 (por analogia, como o LT02 a cita); CN-MA art. 799, VIII | ✓ NT-ATA-NOTARIAL | fluxo, matriz · **plano**: conteúdo de página da internet |
| Ata para usucapião extrajudicial | LRP art. 216-A; CNN arts. 400 a 402 | ✓ NT-ATA-USUCAPIAO | fluxo, matriz · **plano**: requerente casado |
| Ata para adjudicação compulsória | LRP art. 216-B; CNN art. 440-G; CN-MA art. 848 | ✓ NT-ATA-ADJUDICACAO | fluxo, matriz |
| Ata de mediação ou conciliação | Prov. CNJ 67/2018, no CNN (conferir o artigo) | ✗ | — |

## Atos de balcão (fora do livro de notas)

| Ato | Norma | Tela | Ensaio |
|---|---|---|---|
| Cartão de autógrafo (ficha de firma) | CN-MA arts. 864 e 867 | ✓ `/notas/cartoes` | fluxo, matriz · **plano**: estrangeiro com passaporte; quem não assina (a ficha recusa) |
| Reconhecimento de firma por semelhança | CN-MA (como o LT02 cita) | ✓ `/notas/reconhecimento` | fluxo, matriz |
| Reconhecimento de firma por autenticidade e o termo de comparecimento | CN-MA art. 866 | ✓ | fluxo, matriz · **plano**: duas firmas no mesmo documento |
| Reconhecimento em documento de veículo | (item 13.17.3 da tabela) | ✓ | fluxo |
| Reconhecimento de sinal público | CN-MA arts. 870 e 873 | ✓ `/notas/sinais` | fluxo, matriz |
| Autenticação de cópia | CN-MA art. 836 | ✓ `/notas/autenticacao` | fluxo, matriz · **plano**: com ressalva do original (rasura) |
| Autenticação de documento da internet | CN-MA art. 839 | ✓ | matriz |
| Pública forma | CN-MA (por analogia, art. 836) | ✓ `/notas/publica-forma` | fluxo, matriz |
| Apostilamento | Res. CNJ 228/2016 | ✗ | — |
| Materialização e desmaterialização; ato eletrônico (e-Notariado) | Prov. CNJ 100/2020, no CNN (conferir o artigo) | ✗ | — |
| Carta de sentença notarial | CN-MA (conferir o artigo) | ✗ | — |

## O livro, a margem e as centrais

| Ato | Norma | Tela | Ensaio |
|---|---|---|---|
| Termo de abertura e de encerramento do livro | CN-MA (como o LT02 cita) | ✓ `/notas/livros` | `tests/test_notas_livro.py` |
| Termo do livro (o ato como vai ao livro) e o selo | CN-MA arts. 130, 131, 180 e 792 | ✓ `/notas/atos/<id>/termo-livro` | fluxo, matriz |
| Inutilização de folha ou de ato não assinado | CN-MA (conferir o artigo) | ✓ `/notas/atos/<id>/inutilizacao` | `tests/test_notas_inutilizacao.py` · **plano**: a parte não volta para assinar |
| Anotação à margem (revogação, substabelecimento, retificação) | CN-MA art. 831 | ✓ `/notas/anotacoes/pendentes` | `tests/test_notas_anotacoes.py` · **plano** |
| Escritura de retificação e ata retificativa | CN-MA (conferir o artigo) | parcial — sem minuta própria | — |
| DOI à Receita | CN-MA arts. 797 e 800, VII; Lei 10.426/2002, art. 8º | ✓ `/notas/remessas` | `tests/test_notas_doi.py` · **plano**: a compra e venda gera a DOI com as partes certas |
| CENSEC (CEP, RCTO, CESDI) | CN-MA art. 785 | ✓ `/notas/remessas` | `tests/test_notas_censec.py` · **plano**: cada ato entra na central certa |
| Comunicação de venda de veículo | (como a tela cita) | ✓ `/notas/veiculos` | — (precisa da rede, que a trava barra) |
| Consulta à CCN (indisponibilidade) | CNN (conferir o artigo) | ✓ `/notas/ccn` | — (precisa da rede, que a trava barra) |

## Papéis

| Papel | Norma | Tela | Ensaio |
|---|---|---|---|
| Traslado | CC art. 217; CN-MA art. 850 | ✓ `/notas/atos/<id>/traslado` | fluxo, matriz |
| Certidão de inteiro teor | CC art. 217; CN-MA arts. 849 e 851 | ✓ `/notas/certidoes` | fluxo, matriz |
| Certidão positiva e negativa (por busca) | CN-MA arts. 849 e 851 | ✓ | fluxo, matriz |
| Certidão em breve relato | CN-MA art. 851 | ✓ | fluxo, matriz |
| Certidão de testamento: só ao testador, ou com a prova do óbito | CN-MA art. 851, §§ 4º e 5º | ✓ (o tipo de ato) | **plano**: o pedido de terceiro com o testador vivo é recusado |
| Certidão de procuração revogada: com a anotação da revogação | CN-MA arts. 831 e 851 | ✓ | **plano** |

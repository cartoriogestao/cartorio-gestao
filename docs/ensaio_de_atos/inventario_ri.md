# Inventário dos atos — Registro de Imóveis

Pedido do oficial (01/11/2026): o «ensaio de atos», um teste que pratique todos os atos previstos em lei
e nos códigos de normas e confira a saída. Este é o inventário do RI, a terceira atribuição, depois do
RCPN e das Notas (confirmado pelo oficial em 03/11/2026: «primeiro a segunda leva das Notas, depois o
RI»). Para cada ato e cada papel: a norma, se o sistema tem tela, e o que já o pratica.

**As fontes.** Os requisitos elemento a elemento já estão em `docs/REQUISITOS_LEGAIS.md`, seção «Registro
de Imóveis — LT03», e a matriz deles em `tests/test_requisitos_ri.py`: este inventário aponta para lá. Os
artigos do CNN e do CN-MA são os que aquele documento já citou; **os textos dessas normas não estão nesta
máquina**, e o que este inventário acrescenta cita só a Lei 6.015/1973 (LRP), o Código Civil, o CPC e as
leis federais pelo número, com «conferir» onde o artigo do código de normas pesaria.

**O que já pratica o RI.** Como nas Notas, o RI já tinha um ensaio de ponta a ponta antes deste pedido:
`tests/test_fluxo_ri.py` (3 mil linhas) leva cada um dos 25 modelos de ato da casa da prenotação paga
ao termo selado e à certidão (`test_cada_modelo_de_ato_da_casa_lavra_sela_e_sai_igual_no_termo_e_na_certidao`),
e tem a abertura da matrícula, a nota devolutiva com o reingresso, o Livro 3, o encerramento e os
cancelamentos. Mas cada caso é **um só**, e quase sempre isolado: uma compra e venda numa matrícula
limpa. O ensaio desta rodada pratica **as situações** — quem adquire, o que já pesa sobre a matrícula,
a ordem entre os títulos — e **as sequências** na mesma matrícula, que é onde a certidão de propriedade
e a de ônus podem errar.

**Legenda.** Tela: ✓ tem (modelo da casa ou rota própria) · parcial (texto livre na lavratura, sem
modelo; ou falta campo) · ✗ não tem · a conferir. Ensaio: fluxo (`test_fluxo_ri.py`) · matriz
(`test_requisitos_ri.py`) · **plano**: o que esta rodada vai praticar · —.

## Livro 1 — Protocolo, e o que vem antes do registro

| Ato | Norma | Tela | Ensaio |
|---|---|---|---|
| Prenotação e o comprovante do Livro 1 | LRP arts. 174, 182 a 186; CN-MA (como o LT03 cita) | ✓ | fluxo, matriz |
| Prioridade entre títulos contraditórios sobre o mesmo imóvel | LRP arts. 186, 190 e 191 | a conferir | **plano**: dois títulos, o de número menor primeiro |
| Prazo da prenotação e a caducidade | LRP art. 205 | a conferir | **plano** |
| Nota devolutiva (exigências de uma só vez) e o reingresso | LRP art. 198; CN-MA (como o LT03 cita) | ✓ | fluxo, matriz |
| Suscitação de dúvida | LRP arts. 198 a 204 | a conferir | — |
| Indisponibilidade (CNIB): a consulta antes do registro | Prov. CNJ 149/2023 (CNIB, como o modelo cita) | ✓ `/registro-imoveis/cnib` | **plano**: a venda sobre imóvel indisponível é barrada |

## Livro 2 — Matrícula, registro e averbação

| Ato | Norma | Tela | Ensaio |
|---|---|---|---|
| Abertura de matrícula (Livro 2) | LRP arts. 176 e 228 | ✓ | fluxo, matriz |
| Compra e venda | LRP art. 167, I, 29; CC arts. 481 e 1.245 | ✓ R-COMPRA-VENDA | fluxo · **plano**: casal adquirente em comunhão; parte ideal; PJ adquirente; vendedor casado |
| Doação, com reserva de usufruto | LRP art. 167, I, 33 e 7; CC arts. 538 e 1.390 | ✓ R-DOACAO, R-USUFRUTO | fluxo · **plano**: a doação e o usufruto do mesmo título; depois a extinção pelo óbito |
| Permuta | LRP art. 167, I, 30; CC art. 533 | ✓ R-PERMUTA | fluxo |
| Hipoteca e o cancelamento | LRP art. 167, I, 2, e arts. 250 e 251; CC art. 1.499 | ✓ R-HIPOTECA, AV-CANCELAMENTO-HIPOTECA | fluxo · **plano**: a venda com a hipoteca de pé (a certidão de ônus a mantém) |
| Alienação fiduciária e a consolidação | Lei 9.514/1997, arts. 22 a 33; LRP art. 167, I, 35 | ✓ R-ALIENACAO-FIDUCIARIA | fluxo · **plano**: a compra e venda e a fiduciária do mesmo título; a consolidação (art. 26) — a conferir |
| Usufruto e a extinção | LRP art. 167, I, 7, e II, 2; CC art. 1.410 | ✓ R-USUFRUTO, AV-EXTINCAO-USUFRUTO | fluxo · **plano** |
| Título de domínio (regularização fundiária) | Lei 11.952/2009 | ✓ R-TITULO-DOMINIO | fluxo |
| Usucapião (judicial e extrajudicial) | CC arts. 1.238 a 1.244; LRP arts. 167, I, 28, e 216-A | ✓ R-USUCAPIAO | fluxo · **plano**: a extrajudicial, com abertura de matrícula |
| Arrematação e adjudicação judicial | CPC arts. 877, 901 e 903; LRP art. 167, I, 26 | ✓ R-ARREMATACAO, R-ADJUDICACAO | fluxo · **plano**: sobre imóvel penhorado (a penhora sai?) |
| Adjudicação compulsória extrajudicial | LRP art. 216-B | a conferir | — |
| Partilha (inventário, divórcio, dissolução) | CPC arts. 610 e 659; LRP art. 167, I, 25 | ✓ R-PARTILHA | fluxo · **plano**: formal com viúva meeira e herdeiros, cada um com a fração |
| Integralização de capital social | CC arts. 997 e 1.055; LRP art. 167, I, 32 | ✓ R-INTEGRALIZACAO | fluxo |
| Promessa de compra e venda | LRP art. 167, I, 9 e 20 | parcial — sem modelo | — |
| Loteamento e desmembramento urbano | Lei 6.766/1979, art. 18; LRP art. 167, I, 19 | parcial — sem modelo | — |
| Incorporação e instituição de condomínio | Lei 4.591/1964, art. 32; LRP art. 167, I, 17 | parcial — sem modelo | — |
| Servidão | LRP art. 167, I, 6; CC art. 1.378 | parcial — sem modelo | — |
| Bem de família | LRP art. 167, I, 1, e arts. 260 a 265; CC art. 1.711 | parcial — sem modelo | — |
| Locação com cláusula de vigência | LRP art. 167, I, 3; Lei 8.245/1991, art. 8º | parcial — sem modelo | — |
| Cédula de crédito (rural, imobiliária, bancária) | LRP art. 167, I, 13 e 14; Lei 13.986/2020 (conferir) | parcial — Livro 3 e o R-HIPOTECA | — |
| Desapropriação | LRP art. 167, I, 34 (conferir) | parcial — sem modelo | — |
| Construção (habite-se) | LRP art. 167, II, 4 | ✓ AV-CONSTRUCAO | fluxo · **plano** |
| Georreferenciamento | LRP art. 176, § 3º; Lei 10.267/2001 | ✓ AV-GEORREFERENCIAMENTO | fluxo |
| Indisponibilidade (CNIB) averbada | Prov. CNJ 149/2023 | ✓ AV-INDISPONIBILIDADE | fluxo · **plano**: depois dela, a venda barrada |
| Penhora, arresto, sequestro | CPC art. 844; LRP art. 167, I, 5 | ✓ AV-PENHORA | fluxo · **plano**: a certidão de ônus com a penhora |
| Alteração de nome e de estado civil | LRP art. 167, II, 5 | ✓ AV-ESTADO-CIVIL | fluxo · **plano**: o proprietário casa; a certidão de propriedade diz o estado novo |
| Cláusulas restritivas | CC arts. 1.848 e 1.911; LRP art. 167, II, 11 | ✓ AV-CLAUSULAS | fluxo |
| Unificação, fusão, desmembramento — e as matrículas novas | LRP arts. 234 e 235 | ✓ AV-UNIFICACAO | fluxo · **plano**: desmembrar em duas, com a abertura das filhas e o encerramento da mãe |
| Reserva legal / CAR | Lei 12.651/2012, arts. 18 e 29 | ✓ AV-RESERVA-LEGAL | fluxo |
| Cancelamento de ato | LRP arts. 248 a 259 | ✓ AV-CANCELAMENTO | fluxo |
| Encerramento de matrícula | LRP arts. 233 a 235 | ✓ AV-ENCERRAMENTO | fluxo |
| Alteração de logradouro | LRP art. 167, II, 13 | ✓ AV-ALTERACAO-LOGRADOURO | fluxo |
| Retificação administrativa | LRP arts. 212 e 213 | ✓ (tela de retificação) — a conferir | — |
| Inclusão de CPF/CNPJ (averbação de ofício) | LRP art. 176, § 1º, III, 2 (conferir) | a conferir | — |

## Livro 3, indicadores e papéis

| Ato ou papel | Norma | Tela | Ensaio |
|---|---|---|---|
| Registro no Livro 3 (Auxiliar) e a certidão | LRP art. 178 | ✓ | fluxo, matriz |
| Indicador real (Livro 4) e pessoal (Livro 5) | LRP arts. 179 e 180 | ✓ `/registro-imoveis/indicador-real`, `/indicador-pessoal` | **plano**: depois de cada sequência, quem aparece |
| Certidão de inteiro teor da matrícula | LRP art. 19, § 1º | ✓ | fluxo, matriz |
| Certidão de ônus reais e de ações reipersecutórias | LRP art. 19, § 9º (como o LT03 cita) | ✓ | fluxo · **plano**: com a hipoteca, a penhora e a indisponibilidade de pé, e depois de canceladas |
| Certidão de propriedade | LRP art. 19, § 9º | ✓ | fluxo · **plano**: depois do casamento do dono, da partilha e da parte ideal |
| Certidão da cadeia dominial e vintenária | LRP art. 19 | ✓ | fluxo |
| Certidão negativa | LRP art. 19 | ✓ `/registro-imoveis/certidao-negativa` | fluxo, matriz |
| Certidão de transcrição e de prenotação | LRP art. 19, § 10, III | ✗ (o LT03 já registrou) | — |
| DOI do RI | Lei 10.426/2002, art. 8º | ✓ `/registro-imoveis/doi` | **plano**: a compra e venda da matrícula entra com os titulares certos |

## O que não se vai ensaiar, e por quê

- O pedido pela ONR, a CNIB central e a consulta à CNM precisam da rede, que a trava barra. A consulta
  à CNIB pela tela, sobre a base local, entra no ensaio.
- A transcrição do acervo antigo e a importação são migração, não ato.

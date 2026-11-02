# Inventário dos atos — Registro Civil das Pessoas Naturais

Pedido do oficial (01/11/2026): o «ensaio de atos», um teste que pratique todos os atos previstos em lei
e nos códigos de normas e confira a saída. Este é o inventário do RCPN: para cada ato e cada certidão, a
norma, se o sistema tem tela, e se o ato foi ensaiado. O resultado está em `relatorio_rcpn.md`; o teste
em `tests/test_ensaio_de_atos_rcpn.py` (os casos em `tests/ensaio_de_atos_rcpn.py`).

**As fontes.** Os requisitos elemento a elemento, com o artigo, já estão em `docs/REQUISITOS_LEGAIS.md`
(LT01): este inventário não os repete, aponta para lá. Os artigos do CNN (Prov. CNJ 149/2023) e do CN-MA
(Prov. COGEX 28/2026) citados aqui são os que aquele documento já citou a partir dos textos de
`migracao-pg/referencia/`. **Esses textos não estão nesta máquina**: o que o ensaio acrescentou cita só a
Lei 6.015/1973 (LRP), o Código Civil e as leis federais, e o que precisaria do texto do CNN ou do CN-MA
está marcado «conferir». A lei de emolumentos do Maranhão não foi conferida nesta rodada.

**Legenda.** Tela: ✓ tem · parcial (há tela, falta campo que a lei pede) · ✗ não tem.
Ensaio: ✓ praticado nesta rodada · fluxo (praticado por `tests/test_fluxo_rcpn.py`) · — não.

## Registros

| Ato | Norma | Tela | Ensaio |
|---|---|---|---|
| Nascimento no prazo (Livro A) | LRP arts. 50 a 66; CN-MA art. 233 | ✓ `/rcpn/novo/nascimento` | ✓ pais casados; só a mãe (termo negativo); alegação de paternidade; gêmeo; parto em domicílio com duas testemunhas; pai estrangeiro; declarante avó |
| Nascimento tardio | LRP art. 46; CN-MA art. 249; CNN arts. 480 a 494 | ✓ (marca de tardio) | ✓ de maior, com testemunhas; testemunha mais nova que a registrada |
| Nascimento: ordem dos gêmeos | LRP arts. 54, 3º, e 63 | parcial — não há campo da ordem | ✓ |
| Nascimento: dupla maternidade/paternidade, reprodução assistida | Prov. CNJ 63/2017 (no CNN — conferir o artigo) | parcial — os papéis MAE/PAI aceitam (a conferência avisa) | — |
| Natimorto (Livro C-Auxiliar) | LRP art. 53, § 1º; CNN art. 479-A | ✓ `/rcpn/novo/natimorto` | ✓ sem nome (recusado); com nome |
| Óbito no prazo (Livro C) | LRP arts. 77 a 88; CN-MA art. 255 | ✓ `/rcpn/novo/obito` | ✓ viúva com bens e testamento; solteiro sem bens; cônjuge sobrevivente e herdeiro menor; morte violenta; criança; bebê de três meses |
| Óbito tardio | LRP art. 78; CN-MA art. 258 (conflito — ver REQUISITOS_LEGAIS) | ✓ | ✓ declarado pelo neto |
| Óbito de pessoa não identificada | LRP art. 81; CN-MA arts. 255, § 1º, e 257 | parcial — sem os sinais (estatura, idade presumida, vestuário) | ✓ |
| Morte presumida / justificação de óbito | LRP art. 88; CC arts. 6º e 7º | ✗ | — |
| Habilitação, edital (Livro D) e certidão de habilitação | LRP arts. 67 e 43-44; CC arts. 1.525 a 1.532; CNN art. 122 | ✓ `/rcpn/habilitacoes` | fluxo |
| Casamento civil (Livro B) | LRP art. 70; CC arts. 1.533 a 1.536; CN-MA art. 284 | ✓ `/rcpn/novo/casamento` | ✓ cada regime, com e sem pacto; maior de 70; nubente divorciado; viúvo; estrangeiro; 16 e 15 anos; mesmo sexo; sem mudança de nome |
| Casamento: autorização para o nubente de 16 ou 17 anos | CC arts. 1.517 a 1.519 | parcial — não há campo | ✓ |
| Casamento por procuração | CC art. 1.542 | ✗ — não há campo do procurador nem do instrumento | — |
| Casamento em iminente risco de vida (nuncupativo) | CC arts. 1.540 e 1.541; LRP art. 76 | ✗ | — |
| Casamento religioso com efeito civil (B-Auxiliar) | LRP arts. 71 a 75; CC arts. 1.515 e 1.516 | parcial — habilitação tipo RELIGIOSO; o termo usa o modelo do civil | — |
| Conversão de união estável em casamento | LRP art. 70-A; CC art. 1.726 | parcial — habilitação tipo CONVERSAO; a variante do modelo não tem texto | — |
| Livro E — emancipação | LRP arts. 89 a 91; CC art. 5º, par. ún., I | ✓ | ✓ por escritura; por sentença |
| Livro E — interdição / curatela | LRP arts. 92 e 93; Lei 13.146/2015, art. 85 | ✓ | ✓ |
| Livro E — ausência | LRP art. 94 | ✓ | ✓ |
| Livro E — tutela | LRP art. 92, por analogia | ✓ | ✓ |
| Livro E — união estável | LRP art. 94-A; CNN arts. 537 a 539 | ✓ | ✓ por escritura |
| Livro E — opção de nacionalidade | LRP art. 32, § 4º; CF art. 12, I, c | ✓ | ✓ |
| Livro E — tomada de decisão apoiada | CC art. 1.783-A | ✗ | — |
| Traslado de assento lavrado no exterior | LRP art. 32 | ✗ | — |

## À margem

| Ato | Norma | Tela | Ensaio |
|---|---|---|---|
| Averbação (genérica: teor digitado, natureza, fundamento, selo) | LRP arts. 29, § 1º, e 97 a 105; CN-MA arts. 341 e 343 | ✓ `/rcpn/<id>/lancar` | ✓ |
| — divórcio, separação, nulidade e anulação do casamento | LRP art. 29, § 1º, a; CC art. 10, I | parcial — texto livre, sem modelo | ✓ divórcio |
| — reconhecimento de filiação | LRP art. 29, § 1º, d; Lei 8.560/1992 | parcial — texto livre; não atualiza filiação, avós nem nome da certidão | ✓ |
| — alteração de prenome e sobrenome | LRP arts. 56 e 57 | parcial — texto livre; não atualiza o nome da certidão | ✓ |
| — alteração de prenome e gênero | Prov. CNJ 73/2018 (no CNN — conferir o artigo) | ✗ — sem natureza nem sigilo | — |
| — adoção (cancelamento e novo registro) | ECA art. 47 | ✗ | — |
| — mudança do regime de bens | CC art. 1.639, § 2º | parcial — texto livre | — |
| — inclusão de CPF | (art. 347, como o código o cita — conferir a fonte) | ✓ `/rcpn/<id>/averbar-cpf` | — |
| Retificação administrativa (erro evidente) | LRP art. 110; CN-MA arts. 352 e 355 | ✓ (lançamento e modelo de erro material) | ✓ |
| Anotação | LRP arts. 106 a 108; CN-MA art. 369 | ✓ | ✓ óbito anotado no nascimento |

## Certidões

| Certidão | Norma | Tela | Ensaio |
|---|---|---|---|
| Breve relato (nascimento, casamento, óbito, natimorto, Livro E) e o papel de segurança | LRP art. 19; CNN arts. 472 a 477 | ✓ | ✓ todas as espécies acima |
| Inteiro teor | LRP art. 19, § 1º | ✓ (texto colado, que a tela já preenche com o termo; ou reprográfica) | ✓ |
| Inteiro teor de assento com reconhecimento de filiação | Lei 8.560/1992, art. 6º, § 2º; LRP art. 19, § 3º | ✗ — sai como qualquer outra | ✓ |
| Certidão com averbação: a menção e a inscrição | LRP art. 21 e par. único; CN-MA art. 386 | ✓ (a inscrição só quando a alteração não se transcreve — decisão do oficial de 22/10/2026) | ✓ |
| Certidão gratuita | LRP art. 30; CN-MA art. 217 | ✓ | ✓ |
| Certidão negativa | CNN art. 238; CN-MA art. 385 | ✗ | — |
| Certidão eletrônica (CRC) | CNN | ✓ `/rcpn/<id>/certidao-eletronica` | — (precisa da rede, que a trava barra) |

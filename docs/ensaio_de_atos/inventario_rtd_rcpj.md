# Inventário dos atos — RTD e RCPJ

Pedido do oficial (01/11/2026): o «ensaio de atos», um teste que pratique todos os atos previstos em lei
e nos códigos de normas e confira a saída. Este é o inventário do Registro de Títulos e Documentos e do
Registro Civil das Pessoas Jurídicas, a última atribuição da ordem do BRIEFING.

**As fontes.** O inventário ato por ato, etapa por etapa e serviço por serviço da tabela (301 a 323) já
está em `docs/COBERTURA_FLUXOS.md`, seção do RTD/RCPJ (LT05). Os elementos do termo e da certidão estão em
`docs/REQUISITOS_LEGAIS.md` e na matriz `tests/test_requisitos_rtd_rcpj.py`. Este inventário **não
repete** aquele: aponta para lá, e acrescenta as **sequências** e as **situações** que os testes de lá não
variam. Os textos do CN-MA não estão nesta máquina; os artigos vão como aqueles documentos os citam.

**O que já pratica o RTD/RCPJ.** `tests/test_fluxo_rtd_rcpj.py` leva cada ato do protocolo pago ao termo e
à certidão, pelas telas e com a trava do selo pago:
- o registro nos livros B, C e F do RTD e A e B do RCPJ;
- a averbação, o cancelamento, a notificação positiva e a negativa;
- a autenticação de livro contábil, as certidões (por texto, por reprodução, negativa e em breve relato)
  e a gratuidade.

Cada caso é feito num registro limpo.

**Legenda.** ✓ tem · ✗ não tem · a conferir. Ensaio: fluxo (`test_fluxo_rtd_rcpj.py`) · **ensaio**
(`test_ensaio_de_atos_rtd_rcpj.py`) · —.

## As sequências no mesmo registro

| Sequência | Norma | Tela | Ensaio |
|---|---|---|---|
| Cancelamento, e a certidão com o ato que cancelou | LRP arts. 164 e 165; CN-MA art. 994, § 1º | ✓ | fluxo |
| Averbação sobre o registro cancelado: recusada | LRP arts. 128 e 164 a 166 | ✓ | **ensaio** |
| Breve relato da pessoa jurídica dissolvida | CN-MA art. 420, II; LRP art. 165 | ✓ | **ensaio** |
| Breve relato com a leitura da ficha anterior ao último ato | CN-MA art. 420, II | ✓ | fluxo |
| Notificação sobre o registro, positiva e negativa | CN-MA arts. 986 a 989 (como o fluxo cita) | ✓ | fluxo |

## As situações do título e da pessoa jurídica

| Situação | Norma | Tela | Ensaio |
|---|---|---|---|
| Segunda pessoa jurídica com a mesma denominação | CC arts. 1.155, p. ú., e 1.163; CN-MA (conferir) | ✗ sem conferência | **ensaio** |
| Sociedade empresária apresentada ao RCPJ | CC arts. 967, 982 e 1.150; LRP art. 114 | ✗ sem conferência | observação O1 |
| Registro no domicílio das partes | LRP art. 130 | ✗ o título não guarda o domicílio | observação O2 |
| Registro com valor declarado (serviços 305 e 307) | tabela de custas | o item se escolhe à mão; o valor não vai ao selo | observação O3 (o ✗ da cobertura) |
| Notificação por carta com AR ou por edital | CN-MA arts. 990 e 991 | ✗ («ficou para depois») | — (já registrado na cobertura) |
| Certidão em resumo e de informação específica | CN-MA art. 420, I e III | ✗ | — (já registrado na cobertura) |

## O que não se vai ensaiar, e por quê

- O título eletrônico pela Central (ONRTDPJ) vai pela rede, que a trava barra. Tem teste próprio
  (`test_rg_onrtdpj_web`).
- A apostila de Haia é outra funcionalidade (serviço 302).

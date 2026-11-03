# Inventário dos atos — Tabelionato de Protesto

Pedido do oficial (01/11/2026): o «ensaio de atos», um teste que pratique todos os atos previstos em lei
e nos códigos de normas e confira a saída. Este é o inventário do Protesto, a quarta atribuição, depois
do RCPN, das Notas e do RI (a ordem do BRIEFING).

**As fontes.** O Protesto é a atribuição mais coberta da casa. O inventário ato por ato e etapa por etapa
já está em `docs/COBERTURA_FLUXOS.md`, seção «Tabelionato de Protesto (LT04)». Os elementos de cada papel
estão em `docs/REQUISITOS_LEGAIS.md` (seção do Protesto) e na matriz `tests/test_requisitos_protesto.py`.
Este inventário **não repete** aquele: aponta para lá, e acrescenta as **situações** que mudam o ato e
que os testes de lá não variam. Os textos da Lei 9.492/1997, do CNN e do CN-MA que aqueles documentos
citam (`referencia/normas/`) **não estão nesta máquina**; os artigos vão como lá, com «conferir» onde o
código de normas pesaria.

**O que já pratica o Protesto.** `tests/test_fluxo_protesto.py` leva cada ato (apontamento, intimação
pessoal, por edital e eletrônica, protesto, pagamento, desistência, sustação, efeito suspensivo,
cancelamento, certidões e relação) do protocolo pago ao termo, ao selo e ao papel, sempre com **o mesmo
título**: nota promissória, protesto comum por falta de pagamento, devedor pessoa física. Há também cem
arquivos de teste próprios: CRA, CENPROT, tríduo, dois devedores, homônimo, aviso, repasse e outros.

**Legenda.** Tela: ✓ tem · parcial · ✗ não tem. Ensaio: fluxo (`test_fluxo_protesto.py`) · próprio
(arquivo de teste do assunto) · **ensaio** (`test_ensaio_de_atos_protesto.py`) · —.

## As situações do título

| Situação | Norma | Tela | Ensaio |
|---|---|---|---|
| Protesto comum por falta de pagamento | Lei 9.492, arts. 20 a 23 | ✓ | fluxo |
| Protesto por falta de aceite, só antes do vencimento | Lei 9.492, art. 21, §§ 1º e 2º | ✓ (motivo 2) | **ensaio**: depois do vencimento |
| Protesto por falta de devolução | Lei 9.492, art. 21, § 3º | ✓ (motivo 3) | — |
| Protesto para fins falimentares | Lei 9.492, art. 23; Lei 11.101/2005, art. 94; STJ, Súmula 361 | ✓ (tipo F) | próprio (termo) · **ensaio**: observação O1 |
| Cheque: a prova da apresentação ao banco sacado | Lei 9.492, art. 6º | ✗ sem campo | **ensaio** |
| Título apresentado em duplicidade, ou já protestado | Lei 9.492, art. 9º; CRA, irregularidades 52 e 53 | ✗ sem conferência | **ensaio** |
| Duplicata sem aceite (por indicação) | Lei 9.492, art. 8º, p. ú.; Lei 5.474/1968, art. 13 | ✓ (DMI) | fluxo da CRA |
| Título em moeda estrangeira | Lei 9.492, art. 10 | ✓ (tipo de moeda) | — |
| Dois devedores (e o avalista) | Lei 9.492, art. 22 | ✓ | próprio (`test_protesto_dois_devedores`) |
| Devedor pessoa jurídica: a certidão pelo CNPJ | Lei 9.492, art. 27; CNN art. 259 | ✓ | **ensaio** |
| Homônimo: a certidão pelo documento | CNN art. 259 | ✓ | fluxo |
| Devedor falecido | CRA, irregularidade 59 | a conferir | observação O2 |

## As sequências no mesmo devedor

| Sequência | Norma | Ensaio |
|---|---|---|
| Dois protestos, um cancelado: a certidão traz só o outro | Lei 9.492, arts. 26 e 27; CN-MA arts. 944 e 948 | **ensaio** |
| Sustação, revogação e protesto sem nova intimação | Lei 9.492, art. 17 | fluxo |
| Pagamento depois do protesto: recusado; cancelamento pela anuência | Lei 9.492, art. 26; CN-MA art. 942, § 2º | fluxo |
| Efeito suspensivo provisório e definitivo na certidão | CNN art. 263-K | fluxo |

## O que não se vai ensaiar, e por quê

- A remessa e o retorno da CRA, a CENPROT e o Resolve vão pela rede, que a trava barra. Os arquivos de
  exemplo já têm teste próprio.
- O repasse ao apresentante e o boleto são caixa, e têm teste próprio.

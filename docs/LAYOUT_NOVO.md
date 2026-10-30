# O layout novo

Projeto de reorganização das telas, pedido do oficial em 30/10/2026. A implantação vem
por etapas, e cada uma pode ser a última: o sistema continua inteiro em todas.

| Etapa | O que entra | Situação |
|---|---|---|
| Revisão | Nenhuma tela perdida, as portas que faltavam | `docs/REVISAO_DE_TELAS_30_10_2026.md` |
| 1. Casca | Barra de módulos, seções, Novo, Ctrl+K, sino, coluna de apoio | Este documento |
| 2. Ato de Notas | Fases e barra de ação na ficha do ato | A fazer |
| 3. Matrícula | Subabas da ficha, novo ato em fases | A fazer |
| 4. Civil e Protesto | Assento, habilitação, roteiro, dia da CRA | A fazer |
| 5. Operação | Caixa, protocolo, processos, atendimento | A fazer |
| 6. Gestão | Finanças, conformidade, configurações | A fazer |
| 7. Limpar | Tirar a chave e a moldura antiga | A fazer |

## Como funciona

- **As telas não mudam na etapa 1.** Cada uma continua preenchendo `title`, `heading` e
  `content`. Mudou a moldura.
- **A troca é por pessoa.** O botão «Novo layout» fica no rodapé da barra antiga, e
  «Voltar ao layout antigo» no menu do usuário da nova. O padrão de fábrica é o antigo. O
  oficial muda o padrão da casa pelo menu dele.
- **`base.html` decide**: com `layout_novo`, estende `base_novo.html`. O resto de
  `base.html` fica dentro de um `if`, porque o `include` não obedece ao `extends`.

## Tela nova, onde entra

Em `navegacao.py`, e em nenhum outro lugar:

- Tem porta no menu: acrescente em `MODULOS_DA_BARRA`, na seção certa. A entrada leva
  rótulo, rota, papéis e, se houver, o nome antigo e os termos da busca.
- É ficha de uma lista: acrescente em `PAI`, com módulo e seção. Sem isso a barra abre sem
  dizer onde a pessoa está.
- O botão Novo e a busca saem do mesmo registro.

`tests/test_navegacao_registro.py` cobra tudo isso só lendo o código, e compara o registro
com o menu antigo, papel por papel, enquanto os dois existirem.

## O que continua à vista, por ordem do oficial

Selo sem trava, comprovante da gratuidade, ficha sem digitalização, selo cancelado e o aviso
do caixa não vão para o sino. O FERJ/FERC vira faixa fina, sem botão de fechar, e o formulário
(«avisei», data e guia) fica no sino. A palavra continua conferida no servidor.

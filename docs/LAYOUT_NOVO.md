# O layout novo

Projeto de reorganização das telas, pedido do oficial em 30/10/2026. A implantação vem
por etapas, e cada uma pode ser a última: o sistema continua inteiro em todas.

| Etapa | O que entra | Situação |
|---|---|---|
| Revisão | Nenhuma tela perdida, as portas que faltavam | `docs/REVISAO_DE_TELAS_30_10_2026.md` |
| 1. Casca | Barra de módulos, seções, Novo, Ctrl+K, sino, coluna de apoio | Este documento |
| 2. Ato de Notas | Fases e barra de ação na ficha do ato; listas e painel | Pronto |
| 3. Matrícula | Subabas da ficha, novo ato em passos | Pronto |
| 4. Civil e Protesto | Assento, habilitação, roteiro, dia da CRA | Novo registro em passos e habilitação em fases; o resto a fazer |
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

## A ficha em fases

Uma ficha longa vira fases sem mudar de rota nem de formulário, e sem tirar quadro do lugar:

- **O quadro diz a que fase pertence:** `data-fase="teor"` na tag dele. A ordem do HTML continua
  a de quem está no layout antigo, e a ordem na tela sai de `static/casca.css`.
- **A conta mora em Python:** `notas_fases.fases_do_ato` diz as fases, o estado de cada uma, onde
  abrir e o que falta. A rota entrega a função e o molde a chama só no layout novo.
- **A régua é `templates/_fases.html`, e a troca é `static/fases.js`.** O endereço diz a fase
  (`#teor`), e depois de gravar a ficha volta à fase em que estava.
- **Sem JavaScript, a página sai inteira.**
- **Trava de tela não é regra.** Ela orienta quem está na tela. Quem recusa é o servidor, como antes.
- **O que se preenche antes de lançar não mora numa fase que só abre depois.** Se o quadro muda
  de lugar com a situação do ato, quem diz é `lugar_dos_quadros`.

`tests/test_notas_fases.py` cobra que todo quadro tem fase, e `tests/test_ficha_em_fases_web.py`
compara as duas molduras: toda ação e todo endereço de formulário têm de estar nas duas.

**A matrícula usa o mesmo mecanismo, com abas no lugar de fases** (`ri_abas.py`,
`tests/test_ri_abas.py`, `tests/test_ficha_matricula_web.py`). Ela é um registro vivo, sem ordem
própria: a régua não numera nem trava, e abre no Resumo, que começa pelo que espera ação.

**A prenotação também** (`ri_fases_prenotacao.py`): Título, Emolumentos e Qualificação, com o prazo no
título da página. Registro e Entrega, que estavam no desenho, não viraram fases: esta tela não tem esses
quadros, porque o registro é lavrado na matrícula, e ela leva até lá.

**Duas diferenças em relação ao desenho do projeto, e o motivo:**

- A ata continua com a fase Partes. O desenho a tirava, mas o quadro existe e a CENSEC lê as partes.
- Marcar «sem imóvel» não tira a DOI da régua. A coluna `com_imovel` nasce 0, e o 0 de quem marcou é
  igual ao de quem nunca abriu o quadro. Quem tira é o modelo que não transmite imóvel; e a fase
  Lançar avisa quando a escritura está sem imóvel.

## O que continua à vista, por ordem do oficial

Selo sem trava, comprovante da gratuidade, ficha sem digitalização, selo cancelado e o aviso
do caixa não vão para o sino. O FERJ/FERC vira faixa fina, sem botão de fechar, e o formulário
(«avisei», data e guia) fica no sino. A palavra continua conferida no servidor.

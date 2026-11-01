# O layout novo

Projeto de reorganização das telas, pedido do oficial em 30/10/2026. A implantação vem
por etapas, e cada uma pode ser a última: o sistema continua inteiro em todas.

| Etapa | O que entra | Situação |
|---|---|---|
| Revisão | Nenhuma tela perdida, as portas que faltavam | `docs/REVISAO_DE_TELAS_30_10_2026.md` |
| 1. Casca | Barra de módulos, seções, Novo, Ctrl+K, sino, coluna de apoio | Este documento |
| 2. Ato de Notas | Fases e barra de ação na ficha do ato; listas e painel | Pronto |
| 3. Matrícula | Subabas da ficha, novo ato em passos, prenotação e usucapião | Pronto |
| 4. Civil e Protesto | Assento, habilitação, roteiro, dia da CRA | Novo registro em passos, correção em partes, habilitação em fases, ficha do assento em abas e ficha do título de Protesto em fases; o resto a fazer |
| 5. Operação | Caixa, protocolo, processos, atendimento | Ficha do protocolo em abas; o resto a fazer |
| 6. Gestão | Finanças, conformidade, configurações | A fazer |
| Testes | Testes de todas as telas e funções do layout novo: ordem do oficial, 31/10/2026, para vir antes de terminar | Seção «Os testes», abaixo |
| 7. Limpar | Tirar a chave e a moldura antiga | A fazer |

## Como funciona

- **As telas não mudam na etapa 1.** Cada uma continua preenchendo `title`, `heading` e
  `content`. Mudou a moldura.
- **A troca é por pessoa.** O botão «Novo layout» fica no rodapé da barra antiga, e
  «Voltar ao layout antigo» no menu do usuário da nova. Desde 30/10/2026, por decisão do
  oficial, o padrão de fábrica é o novo: quem não escolheu abre nele, com um aviso de «Ficar
  neste» ou «Voltar ao antigo». O oficial pode devolver a casa ao antigo pelo menu dele.
- **A suíte de testes fica na moldura antiga** (`tests/conftest.py`), porque os testes de
  tela leem o HTML dela. Quem testa a moldura nova a pede por pessoa. Ver «Os testes».
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

## O formulário em passos e a tela em quadros

**Formulário longo vira passos, e continua um formulário só.** A régua é `<nav data-cg-passos="<id do form>">`,
com botões `data-passo-ir`, e cada parte é um `data-passo`. `static/fases.js` mostra a parte aberta, abre sozinho
a parte de um campo recusado e, ao trocar de passo, volta ao começo dele. Sem JavaScript, o formulário sai inteiro.
`templates/_passos_e_gravar.html` traz a régua e a barra de gravar presa ao pé da tela. Exemplos:
`atrib_rcpn_novo.html`, `atrib_protesto_novo.html`, `ri_protocolo.html`.

**Tela sem ordem nem fase vira quadros recolhidos.** `templates/_quadros_recolhidos.html` traz `abre` e
`ferramentas`. O título do quadro diz como ele está, sem abrir, e nunca leva segredo. O que está recolhido vai junto
ao gravar; um campo inválido em quadro fechado abre o quadro; o endereço abre o quadro (`#cfg-centrais`); e depois de
gravar a tela volta com os mesmos quadros abertos. Exemplos: `settings.html`, `nfse_gestor.html`, `protesto_avisos.html`.

**Regra das duas.** Só muda o layout novo, por `{% if layout_novo %}`, e o estilo fica em `<style>` no próprio molde.
O HTML do layout antigo continua igual, e os dois layouts mandam os mesmos campos: compare antes de abrir o PR.

## Os testes

Ordem do oficial, 31/10/2026: «antes de terminar tudo, precisamos elaborar testes para todas as telas e funcoes do novo
layout». A lista de telas não se escreve: sai da tabela de rotas do sistema, e tela nova entra sozinha.

| Arquivo | O que cobra |
|---|---|
| `tests/test_layout_todas_as_telas.py` | Toda rota de leitura, nas duas molduras e com os quatro papéis: nada dá erro, a moldura é a escolhida, as duas oferecem os mesmos formulários, fases e passos têm porta e quadro, todo link e todo formulário levam a uma rota, o menu de cada papel não leva a recusa |
| `tests/test_layout_todos_os_formularios.py` | Todo formulário de toda tela, mandado como a tela vem e preenchido, e todo filtro de lista: erro de regra é aviso, e não erro 500 |
| `tests/test_layout_no_navegador.py` | Chrome de verdade: toda tela em 1920x1080 e 1366x768 sem erro de script nem estouro, cada aba mostra só os quadros dela, cada porta mostra o bloco dela, o campo obrigatório vazio abre o passo dele, busca, Novo, sino, gavetas, teclado e troca de layout |
| `tests/test_layout_fichas_*.py` | Cada ficha em fases ou abas, em cada estado do rito: a fase em que abre, o que está travado, o que espera ação |
| `tests/test_layout_semente.py` | Toda rota com número no endereço tem semente, ou tem o motivo escrito |
| `tests/test_layout_moldes.py` | Sem banco: toda fase citada num molde existe no módulo da ficha, todo quadro fecha, toda classe da casca tem regra |
| `tests/test_layout_ensaio.py` | Sem banco: a trava barra de verdade, e cada guarda acusa o defeito para o qual existe |

**A casa de ensaio** (`tests/layout_casa.py`) é uma serventia fictícia com uma linha de cada coisa que tem tela. A base é a
carga do sandbox, e cada atribuição tem a sua `tests/layout_semente_*.py`. Rota nova com número no endereço fica vermelha em
`test_layout_semente` até ganhar semente, ou um motivo em `SEM_SEMENTE`.

**A trava** (`tests/layout_ensaio.py`) é o que permite mandar todo formulário numa máquina que pode ser a da produção. Um gancho
de auditoria do Python barra, no processo inteiro: rede, programa de fora, gravar fora da pasta temporária e ler a pasta de uma
instalação real. O banco fica de fora, e por isso `conferir_que_e_banco_de_teste` recusa o DSN que não for de teste. O que a
trava barra não é defeito, mas o erro que a rota levanta por causa da falta de rede é: a Central fora do ar é coisa de todo dia.

**Como rodar.** São testes `lento`: `--completa` os leva, e `--rapida` não. Para só estes, com o DSN de teste no ambiente
(`CG_TEST_BACKEND=pg`, `CG_PG_DSN`):

```
python -m pytest tests/test_layout_todas_as_telas.py tests/test_layout_todos_os_formularios.py tests/test_layout_no_navegador.py tests/test_layout_semente.py tests/test_layout_moldes.py tests/test_layout_ensaio.py tests/test_layout_fichas_ri.py tests/test_layout_fichas_civil.py tests/test_layout_fichas_notas.py tests/test_layout_fichas_protesto.py tests/test_layout_fichas_rcpj.py tests/test_layout_fichas_gestao.py -n 4 --dist loadfile
```

Sem o Playwright ou sem navegador, `test_layout_no_navegador` pula e diz por quê. `CG_LAYOUT_AREAS=ri` e `CG_LAYOUT_PAPEIS=ADMIN`
encurtam a rodada de quem está mexendo numa área. `CG_LAYOUT_ALTURAS=<prefixo>` grava a altura de cada tela, da maior para a menor, em
`<prefixo>_1920.txt` e `<prefixo>_1366.txt`. Só informa: a altura depende do dado, e o que é alto demais quem decide é quem usa a tela.

**A suíte inteira na moldura nova.** `tests/conftest.py` fixa a moldura antiga, porque muitos testes leem o menu dela. Com
`CG_TESTE_MOLDURA=novo`, ela roda toda na casca. O que fica vermelho aí e verde na antiga é teste lendo o menu antigo, ou defeito:
compare as duas listas antes da etapa 7.

**Antes da etapa 7, rode também esta conferência à mão:** a varredura de formulários manda o que a tela entrega, mas não diz se o
ato ficou certo. Quem diz são os testes de cada módulo, e a suíte com banco precisa estar verde.

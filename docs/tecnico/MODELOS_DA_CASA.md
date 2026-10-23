# Os modelos de todos os papéis da casa

> **Estado em 19/09/2026 (Fase 0):** o catálogo tem **34 chaves** (`len(modelos_da_casa.CATALOGO)`). Contagens antigas neste arquivo («10», «15», «RCPJ = 0») são históricas. Matriz viva: [MATRIZ_DE_PAPEIS.md](MATRIZ_DE_PAPEIS.md). Inventário: `tools/inventario_modelos.py`.
>
> **Moldes ODT do RCPN** (`RC_MOLDE_*`) moram em `modelos_moldes.py` / `mo_moldes`, não no `CATALOGO` de texto — ver [MATRIZ_DE_PAPEIS.md](MATRIZ_DE_PAPEIS.md).
>
> **Checklist — novo ato/papel:** (1) existe piso (constante ou ODT)? (2) acrescentar chave em `CATALOGO` com `tipo`; (3) ligar emissão a `corpo_de`/`padrao_de`; (4) rodar inventário exit 0; (5) teste de import do `padrao`. Sem piso → só pendência na matriz, sem inventar prosa.

*29/08/2026 — resposta ao relato **#28** do oficial.*

> «preciso de mais controle sobre os modelos de todos os atos, de todas
> atribuições. preciso ter controle geral sobre os modelos, em especial os
> cabeçalhos padrão de cada atribuição e ato, corpo, encerramento, eventual
> notas de rodapé»

---

## O que se mediu antes de mexer

Havia **duas realidades convivendo**, e nenhuma delas atendia ao pedido.

**Quatro modelos do Registro de Imóveis já liam de tabela** — cabeçalho, ficha,
certidão e nota devolutiva —, caindo no padrão do código quando ela estivesse
vazia (`modelo["corpo"] if modelo else MODELO_CERTIDAO_PADRAO`). E `ri_modelos`
está com **zero linhas**: na prática os quatro saíam do código.

**Cinco não liam de lugar nenhum.** O **recibo**, o **orçamento** e o
**comprovante de recepção** do caixa, o **traslado** das notas e o
**comprovante de prenotação** do RI eram `env.from_string(MODELO_RECIBO)` —
constante do programa, direto para o papel. Para mudar uma vírgula em qualquer
um deles era preciso mexer no código e empacotar uma versão.

E `nt_modelos` tem **333 linhas**, mas aquilo é outra coisa: são as minutas das
escrituras, o **corpo do ato**, com os campos da CENSEC. Não são o papel que a
casa imprime — e por isso não entraram aqui.

| | antes | agora |
|---|---|---|
| papéis editáveis pelo oficial | 4 (só do RI) | **9, das três atribuições que emitem papel** |
| telas onde se edita modelo | 2, ambas dentro do RI | **1, no Administrativo** |
| papéis presos no código | 5 | 0 |

---

## O desenho, e ele é o que a casa já fazia

**O código é o piso; a tabela é o ajuste.** Sem linha em `mo_modelos`, vale o
modelo escrito no programa — exatamente como os quatro do RI já funcionavam. O
que mudou foi estender essa regra aos nove e pôr todos numa tela só.

Isso dá três coisas de graça:

1. **nada se perde** — o padrão não é apagável, porque não mora no banco;
2. **«voltar ao padrão» é apagar a linha**, e não recadastrar um texto que
   ninguém tem mais guardado;
3. **instalação nova já nasce funcionando**, sem carga de modelos.

O catálogo guarda **onde o texto de fábrica mora** (módulo e nome), e não o
texto. Copiá-lo para cá faria duas versões do mesmo modelo, e elas divergiriam
no primeiro conserto — a tela mostrando uma coisa e o programa imprimindo
outra. **Este projeto já pagou por isso com a `normalizar_nome`.**

## Uma tabela só, e não uma por módulo

O pedido é «controle geral». Espalhar por `ri_modelos`, `cx_modelos` e outras
daria quatro telas, e a pergunta *«onde eu mudo o cabeçalho?»* continuaria sem
resposta — que é o relato.

`ri_modelos` continua sendo lida **como legado**: ela tem zero linhas nesta
casa, mas uma instalação que já tivesse ajustado alguma coisa ali não pode
perder o ajuste ao subir de versão. Quando os dois existem, quem manda é o
ajuste novo — senão editar na tela não teria efeito, e o operador não saberia
por quê.

---

## Três coisas que a construção achou

### 1. O `MODELO_PADRAO` da etiqueta se chama modelo e não é um

`notas_selo.MODELO_PADRAO` estava na varredura das constantes, com 37
caracteres: é `https://selo.tjma.jus.br/?selo={selo}` — a **URL que vai dentro
do QR**, com marcador do `str.format` e não do Jinja.

Posto no catálogo, a tela o ofereceria como corpo de papel e a conferência o
passaria pelo Jinja, que é o motor errado: `{selo}` não é sintaxe de Jinja, e a
conferência **aprovaria um texto que o QR não sabe montar**. Ficou de fora, e
o motivo ficou escrito ao lado. É a lição de sempre: **a mesma palavra em dois
lugares não quer dizer a mesma coisa.**

### 2. Duas telas para a mesma coisa, uma delas perdendo em silêncio

Com o catálogo de pé, a tela antiga do RI (`/registro-imoveis/modelos`)
continuava editando `ri_modelos` — que agora é só legado. Com um ajuste gravado
na tela nova, **o que se editasse lá não teria efeito nenhum e ninguém saberia
por quê.**

Ela leva para a tela geral, com um recado dizendo para onde os modelos foram. E
o corpo dela foi **apagado, e não desligado**: função pronta sem rota é peça
esperando alguém religá-la sem saber por que ela existia — já aconteceu cinco
vezes neste projeto.

### 3. O que ela tinha de melhor não se perdeu

A tela antiga conferia o modelo **contra uma matrícula de verdade**, e isso é
melhor que o boneco de ensaio: o boneco pega erro de forma — chave que não
existe, `for` sem fechar, filtro escrito errado — e **não pega campo que só
aparece em ficha com ato, com ônus, com parte**.

Ela virou um conferidor registrado pelo próprio RI, que a tela geral chama para
os quatro papéis dele. Sem matrícula nenhuma no banco ele devolve «não tinha com
que conferir», e aí vale o boneco — que é o caso da instalação nova.

> `""` («conferi e está bom») e `None` («não tinha com que conferir») são
> coisas diferentes. Tratá-las como a mesma faria a instalação nova passar sem
> conferência alguma.

---

## A conferência vem antes de gravar, e recusa

Gravar primeiro e avisar depois deixaria o modelo quebrado valendo até alguém
voltar na tela — e **quem descobre é o escrevente com o cliente na frente**, na
hora de emitir. Aqui o erro aparece para quem edita, que é quem sabe consertá-lo.

Ela roda no **mesmo ambiente restrito** do resto da casa
(`SandboxedEnvironment`): conferir num ambiente mais solto aprovaria modelo que
a hora do ato recusa.

E **corpo vazio não se grava** — ele volta ao padrão. Guardar vazio faria a casa
imprimir folha em branco, e folha em branco assinada é pior que modelo feio.

---

## O varredor que fica

`test_todo_papel_do_catalogo_e_consultado_por_alguma_tela` procura cada chave no
código das telas. **O defeito que mais se repetiu neste projeto é a função
pronta que nenhuma tela chama; aqui ele teria outra cara**: um modelo editável
na tela que o documento ignora — o oficial ajusta, imprime, e sai o de antes.

Ele já pagou: quando eu havia convertido só a certidão, foi ele que apontou os
outros três papéis do RI que ainda liam direto da tabela velha.

E `test_todo_padrao_do_catalogo_existe_de_verdade` vai buscar cada constante
onde o catálogo diz que ela mora. Sem ele, renomear uma constante deixaria o
catálogo apontando para o nada, e **a tela mostraria um modelo vazio como se
fosse o padrão da casa**.

---

## O que ainda não entra aqui

- **As 333 minutas de escritura** (`nt_modelos`) — são o corpo do ato, não o
  papel. Elas têm tela própria nas Notas.
- **Os textos que o RCPN, o Protesto e o RCPJ/RTD montam por campo** — a
  certidão do civil no modelo do CNJ, a certidão de protesto, a de inteiro teor.
  Ali não há um modelo a editar: o texto se **monta dos campos medidos**, e um
  campo fora do lugar não é questão de gosto, é certidão errada.
- **A URL de dentro do QR do selo**, pelo motivo acima.

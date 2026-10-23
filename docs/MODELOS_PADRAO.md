# Modelos fora do código — a base dos padrões

> LF06A, 19/10/2026. Pedido do oficial: «Não deveríamos ter modelos no código;
> deveriam estar no banco, para editar com mais facilidade.»
>
> **Os lotes LF06B a LF06G leem este arquivo** antes de mexer, junto com
> [`MODELOS_INVENTARIO.md`](MODELOS_INVENTARIO.md), que diz o que falta migrar.

## Onde mora cada coisa

| o quê | onde | quem muda |
|---|---|---|
| o **texto de fábrica** (o padrão) | `modelos_padrao/<pasta>/<CHAVE>.txt` | o programa, numa versão nova |
| a **ficha** do papel | `modelos_padrao/<pasta>/<CHAVE>.json` | o programa |
| o que é **código** no catálogo | `modelos_papeis/<pasta>.py` e `modelos_papeis/tipagem.py` | o programa |
| a **base dos padrões** (cópia da pasta) | schema do PostgreSQL `modelos_padrao` — ver «O nome do schema» | a subida, sozinha |
| o **ajuste da casa** | `mo_elementos` (a tela grava aqui) e `mo_modelos` (legado) | a casa, na tela de Modelos |

As pastas de hoje são `ri`, `caixa`, `notas`, `rcpj_rtd`, `rcpn` e `protesto` — o
nome do módulo em `modelos_papeis/` —, e, desde o LF06G, `retificacao` e
`usucapiao`, cujos papéis são do **Registro de Imóveis** (ver o passo 4).

**O padrão e o ajuste nunca moram juntos.** A base dos padrões é apagada e
recriada inteira quando a pasta muda; ela não guarda nada da casa (o teste
`test_a_base_nao_guarda_nada_da_casa` confere). Por isso uma atualização
**nunca sobrescreve um ajuste**: ela troca a base, e o ajuste está noutro lugar.

## O formato

### `<CHAVE>.txt` — o corpo

- UTF-8, **exatamente** o texto que o papel usa — nem uma linha a mais no fim.
  A impressão digital (sha256) é deste arquivo; um editor que acrescenta
  quebra de linha no fim muda o padrão, e o git mostra.
- Quebra de linha `\n`. Se o git do Windows trouxer `\r\n`, a leitura desfaz
  (`modelos_papeis/pasta.py`), e o `.gitattributes` (`modelos_padrao/** -text`)
  já impede a conversão.
- O formato dos claros é o da ficha:
  - `JINJA` — `{{ a.numero }}`, com laço e condição, no `SandboxedEnvironment`;
  - `CHAVES` — `{numero}` do `str.format`, sem lógica (termos do civil,
    protesto, RCPJ/RTD);
  - `ODT` — o papel é um formulário: o arquivo é `<CHAVE>.odt`, binário, como
    está; na base o corpo vai em base64 e a impressão digital é a do binário.

### `<CHAVE>.json` — a ficha

```json
{
  "chave": "CAIXA_RECIBO",
  "atribuicao": "Caixa e protocolo",
  "nome": "Recibo",
  "formato": "JINJA",
  "explica": "A prova de pagamento do atendimento inteiro.",
  "campos": ["agora", "data_extenso", "documento", "emitido_por", "funcao",
             "fundos", "itens", "lancamento", "observacao", "r", "sv",
             "telefone", "tem_fundos"]
}
```

- `atribuicao` é o rótulo por extenso, o mesmo de `modelos_papeis/<pasta>.ATRIBUICAO`.
- `nome` e `explica` são o que a tela de Modelos mostra. **Moram só aqui** — o
  catálogo os lê da ficha (`modelos_papeis/pasta.completar`).
- `campos` são os claros que o padrão USA, medidos no texto
  (`pasta._campos`). Não são a conferência: quem recusa claro inventado é o
  módulo do papel (ex.: `rc_modelos_do_livro.conferir_corpo`).

### A peça — `<CHAVE>__<peca>.txt`

O que **não** vai para o texto editável é a REGRA jurídica que decide se uma
frase entra (edital × pessoal, plural, gêmeos…): ela fica no código. O **texto**
de cada frase pode ir para a pasta como peça do papel:

    modelos_padrao/protesto/PT_TERMO_PROTESTO__edital.txt

- dois sublinhados separam o papel da peça (um só já aparece nas chaves);
- o papel em maiúsculas, a peça em minúsculas (`pasta.chave_normal`);
- sem `.json` próprio, a peça herda a ficha do papel (atribuição, formato) e
  mede os próprios claros;
- o código lê com `MODELOS.texto_do_papel(con, "PT_TERMO_PROTESTO__edital")`
  (ajuste em `mo_modelos` com essa chave → padrão), ou `padrao_de` sem `con`;
- a peça **não tem linha na tela de Modelos** (a tela lista o catálogo); o
  ajuste dela se grava em `mo_modelos` com a chave da peça
  (`MODELOS.salvar(con, "US_NOTIFICACAO__silencio", …)`), e a busca o acha;
  quando a casa precisa EDITAR as frases na tela, o LF06F fez um papel com
  PARTES (`===NOME===`, como os teores do RCPJ/RTD): `RCPJ_RTD_PDF_MOLDURA` e
  `CAIXA_WHATSAPP` — a parte apagada no ajuste volta ao padrão;
- frase com claro (`CHAVES`) se preenche com `MODELOS.preencher(chave, texto,
  valores)`, que recusa o claro desconhecido com o nome do papel — a mesma
  régua (`conferir_claros`) que a tela usa no conferidor do módulo (LF06G).
- **a peça é a frase, e a cola é do código** (LF06C): o espaço que gruda a
  frase na anterior, a vírgula solta e o conectivo de uma palavra («e», «em»)
  ficam no módulo. A peça não começa nem termina em branco — o ajuste da casa
  é gravado com `strip()`, e uma peça que começasse com o espaço o perderia
  no primeiro ajuste (`test_a_peca_e_a_frase_e_a_cola_fica_no_codigo`).
  Começar com «, » pode.

**Medido no LF06E (19/10/2026): a peça `__` é lida, mas não é editável.** A
tela de Modelos, `modelos_elementos`, `modelos_elementos_web`, `modelos_previa`
e `livro3_modelos_web` põem a chave em maiúsculas (`PT_TERMO_PROTESTO__EDITAL`),
e o catálogo não a acha — `?editar=` diz «não existe nesta casa». Por isso o
Protesto registrou cada frase como **linha do catálogo, com ficha própria** e
chave em maiúsculas (`PT_TERMO_INTIMACAO_EDITAL`), marcada
`'peca': True, 'elementos_comuns': False` (ver `modelos_papeis/protesto.py`):
aparece na tela, edita como qualquer papel, e o encerramento da atribuição não
entra no meio da frase. O guarda do esqueleto pula a peça (frase curta não é
papel sem texto). A tela confere a peça ao gravar com a régua de quem a
preenche (`protesto_pecas.conferir`, registrado em `conferidores_de_modelo`):
os claros que o padrão usa — medidos iguais aos que o montador passa, chamada
por chamada do ouro.

**O termo lavrado no livro sai do PADRÃO das peças** (revisão do LF06E, 2ª
volta). A frase da intimação e o motivo e o tipo por extenso eram constantes,
e o ajuste da casa não chegava ao Livro de Registro de Protestos; fazê-lo
chegar muda o que se lavra, e isso é regra de negócio. `protesto.lancar_protesto`
chama `TERMO.montar` sem `con`. A peça aparece e edita na tela, e a ficha diz
que o livro lavra o padrão; a certidão e o instrumento, que se emitem de novo a
cada pedido, seguem o ajuste. Se o oficial confirmar que o livro segue, basta
passar `con=con` (teste `test_o_protesto_lancado_lavra_o_padrao_e_nao_o_ajuste_da_casa`).

### A peça-vocabulário — `nome = texto`

O rótulo que vai ao papel também é texto («FALTA DE PAGAMENTO», o nome da
espécie, «pago por cheque»). Os dicionários do Protesto viraram peças de uma
linha por rótulo (`PT_TERMO_MOTIVOS`, `PT_ESPECIES`, `PT_LIVRO_PAGAMENTOS`, a
moldura do papel impresso `PT_MOLDURAS`…), lidas por
`protesto_pecas.vocabulario(con, chave)` (ou `rotulos`, que já preenche):

- **o nome é do sistema, o texto é do oficial** — os nomes que valem são os do
  padrão; nome que o ajuste inventa não entra (QUAIS códigos existem continua
  sendo regra, no código: `MOTIVOS_DO_PROTESTO`, `FORMAS_DE_PAGAMENTO`…);
- linha que o ajuste apagou, ou deixou sem texto, volta ao padrão;
- o pedaço com claro (`credor = credor {credor}`) se preenche com
  `protesto_pecas.preencher`; claro inventado é recusa com o nome da peça.

## A base dos padrões

### A carga (a subida)

`ri_schema.init_ri_schema` — que roda em toda subida — chama:

1. `modelos_da_casa.trazer_ajustes_do_legado_ri(con)`: o que a tabela velha
   `ri_modelos` tiver vira ajuste em `mo_modelos` (zero linhas nesta casa). O
   ajuste novo vence o legado, e a linha velha é desligada (`ativo = 0`), para
   «voltar ao padrão» não ressuscitá-la na subida seguinte.
2. `modelos_da_casa.subir_base()` → `carregar_base()`:
   - conexão **própria** com o PostgreSQL (não entra na transação da casa nem
     na gravação do banco novo do `banco_pg`);
   - `pg_advisory_xact_lock(hashtext('modelos_padrao.carga:<schema>'))` — vários
     processos sobem juntos; só um carrega, os outros esperam e leem;
   - compara a **marca** (sha256 de todos os `.txt/.json/.odt` da pasta) com a
     gravada em `padroes_marca`; se for a mesma, não mexe em nada;
   - se mudou: `DROP SCHEMA … CASCADE`, `CREATE SCHEMA`, as duas tabelas e os
     padrões, **numa transação só** — quem lê vê a base velha ou a nova;
   - `lock_timeout` de 30 s; a base que não carrega **não derruba a subida**.

As tabelas:

    padroes(chave PK, atribuicao, nome, formato, corpo, campos jsonb, explica,
            impressao_digital /* sha256 do corpo */, carregado_em)
    padroes_marca(marca PK, quantos, carregada_em)

### A leitura

Cada processo lê a base **uma vez** (`modelos_da_casa._padroes`) e guarda. O
padrão só muda numa atualização, e a atualização reinicia o serviço.

Sem PostgreSQL ligado (ferramenta avulsa), ou com a base fora do ar, o processo
serve a **pasta** — a fonte de onde a base é carregada, os mesmos bytes — e a
tela de Modelos avisa «A base de padrões não carregou neste servidor».

### O nome do schema

Segue a instalação, com a mesma regra do `banco_pg` (`CG_PG_SCHEMA` ganha):

| instalação | schema da casa | base dos padrões |
|---|---|---|
| produção | `producao` (`CG_PG_SCHEMA=producao`) | `modelos_padrao_producao` |
| ensaio no mesmo banco | `ensaio_final` | `modelos_padrao_ensaio_final` |
| testes, cópia de desenvolvimento | `cg_<hash do caminho>` (sem `CG_PG_SCHEMA`) | `modelos_padrao` — um por banco |

Duas instalações no mesmo banco não podem dividir a base: cada subida apagaria
a da outra, e a produção imprimiria o padrão do ensaio. Nos testes, cada
trabalhador da suíte tem o seu banco (`cartorio_teste_<n>`) e os processos dele
rodam o mesmo código — a mesma pasta, a mesma marca.

## A busca única

    modelos_da_casa.texto_do_papel(con, chave)

1. o **ajuste ativo da casa** — o corpo do ato em `mo_elementos` (o que a tela
   grava), senão `mo_modelos` (legado), com encerramento e rodapé compostos por
   `modelos_elementos.montar_documento`;
2. o **padrão da base** — `padrao_de(chave)`;
3. **erro claro** — `ModeloError`: «O padrão «X» não está carregado na base de
   modelos (…): falta o arquivo modelos_padrao/…/X.txt …». Nunca folha em branco.

`corpo_de(con, chave)` é a mesma busca com o nome antigo — os sítios que já a
chamavam continuam chamando. Outras funções:

| função | para quê |
|---|---|
| `padrao_de(chave)` | só o padrão da base, sem `con` (o «sem modelo → padrão» dos montadores) |
| `impressao_digital_de(chave)` | o sha256 do padrão de hoje |
| `arquivo_do_padrao(chave)` | o caminho na pasta (a tela mostra) |
| `padrao_mudou_depois_do_ajuste(con, chave)` | `MUDOU` / `IGUAL` / `SEM_MARCA`, e a diferença |
| `situacao_da_base()` | de onde os padrões saem neste processo (base ou pasta) |
| `constante_antiga(modulo, nome)` | o `__getattr__` dos módulos que guardavam o texto |
| `conferir_claros(texto, conhecidos)` | o que há de errado nos `{claros}` de um texto `CHAVES` (a tela e o montador) |
| `preencher(chave, texto, valores)` | o `str.format` do papel `CHAVES`, com `ModeloError` legível no lugar do `KeyError` |

**O nome antigo continua respondendo.** `ri_odt.MODELO_FICHA_PADRAO`,
`protesto_termo.TERMO_DO_PROTESTO`, `rg_teor_rtdpj.PADROES_POR_CHAVE`… devolvem
o padrão da base, pelo `__getattr__` do módulo. Dentro do próprio módulo o nome
solto não existe mais — lá se chama `padrao_de`.

## Quando o padrão muda numa versão nova

1. O `.txt` muda no git — a diferença de cada vírgula fica à vista.
2. A subida vê a marca nova e recarrega a base.
3. **O ajuste da casa não muda.** Ele guarda em `base_impressao` (em
   `mo_elementos` e em `mo_modelos`) o sha256 do padrão sobre o qual foi feito.
4. A tela de Modelos compara: se o padrão de hoje não é aquele, avisa **«O
   padrão mudou depois do seu ajuste»** e mostra a diferença entre o ajuste e o
   padrão de hoje (o texto antigo do padrão não fica guardado; só a marca dele).
   A casa decide se traz a mudança para o ajuste ou volta ao padrão.
5. Ajuste anterior ao LF06A (`base_impressao` nulo — o cartão de autógrafo da
   produção é um): a tela diz que não há como saber. Gravar de novo passa a
   marcar.

## Voltar ao padrão

Na tela de Modelos, **«Voltar ao padrão do sistema»** apaga o ajuste da casa
(`mo_elementos` e `mo_modelos`). O papel volta a sair da base. A base nunca é
editada pela casa — por isso o padrão não se perde, e não é preciso recadastrar
texto nenhum.

## O que o LF06D acrescentou (Notas, 19/10/2026)

Os textos das Notas eram f-strings com regra no meio, e não constantes. O que
ficou combinado, para quem vem depois:

- **A peça tem ficha própria.** Cada `<CHAVE>__<peca>.txt` das Notas tem o seu
  `.json`: o formato dela é `CHAVES` (o montador a preenche com `str.format`,
  mesmo quando o papel-pai é Jinja) e o `explica` diz **quando a regra a
  escolhe**. A peça sem ficha continua herdando a do papel.
- **Papel que é pedaço de papel** (a fórmula da etiqueta, a abertura do teor,
  a qualificação) declara no catálogo `'elementos_comuns': False` — o
  encerramento e o rodapé da atribuição não entram no meio de um teor — e
  `'so_claros_do_padrao': True`: a tela (`modelos_elementos.conferir`) recusa o
  claro que o padrão não usa, porque o montador não o preenche. A régua é a
  `conferir_claros` (LF06G), a mesma do `preencher` — a tela e o balcão dão o
  mesmo recado do mesmo texto.
- **`padrao` sem constante.** Texto que era f-string não tinha nome antigo: o
  par diz a FUNÇÃO que monta o papel (`('notas_teor', 'qualificar')`), e o
  teste confere que o módulo dela lê a chave. Entrada de dicionário antigo
  leva o nome com o índice: `('notas_teor', 'ABERTURAS["ESCRITURA"]')`.
- **O montador puro lê pelos textos da montagem**: `T = MODELOS.textos(con)`;
  `T(chave)` é o texto, `T.preencher(chave, **claros)` o preenche. `con` pode
  ser a conexão (vale o ajuste da casa), quem a abre (`db.connect`, na rota
  que não tem uma aberta) ou nada (o padrão — o teste e a ferramenta). Cada
  texto é lido uma vez por montagem. Claro que o montador não preenche vira
  `ModeloError` com o nome do papel, e não `KeyError` (`T.preencher` usa o
  `preencher` do LF06G, a mesma régua da tela).
- **Quem GRAVA o texto passa `con`** — o termo do livro, a margem, a fórmula
  do reconhecimento, a certidão. Sem ela a montagem lê só o padrão, e o ajuste
  da casa nunca chega ao papel (foi o que a revisão do LF06D achou em
  `notas_anotacoes.anotar` e nas telas da certidão). E o `ModeloError` vira a
  recusa do módulo, que a rota já mostra (`LivroError`, `AnotacaoError`,
  `CertidaoNotasError`) — com cuidado onde o módulo engole a própria recusa:
  `anotar_ato_anterior` engole «já anotada», e por isso a margem que não monta
  é `ModeloDaMargemError`, que ele deixa passar (o lançamento volta junto).
  **Dado gravado que não é papel** (`nt_livros.descricao`) continua saindo do
  padrão: mudá-lo pelo ajuste é pergunta para o oficial.
- **A regra fica no código, a frase vai inteira para a peça**: «RECONHEÇO POR
  SEMELHANÇA AS FIRMAS DE {quem}. DOU FÉ.», e não «AS FIRMAS» solto — a peça
  tem de ser legível sozinha.
- **O cabeçalho da serventia continua no código** (decisão do oficial de
  07/09/2026) e entra no papel pronto, num claro (`{cabecalho}` do termo de
  comparecimento).
- **Fórmula curta não é esqueleto.** O guarda das dez palavras
  (`test_todo_padrao_do_catalogo_existe_de_verdade`) tem a lista
  `FORMULA_CURTA` — a fórmula do reconhecimento tem oito palavras, todas à
  vista.

### As minutas das Notas

As 33 minutas de fábrica (`notas_modelos`) moram em
`modelos_padrao/notas/minutas/<codigo>.txt` (o corpo, já corrido) e `.json` (a
ficha, com o nome; atribuição «Tabelionato de Notas — minutas»). **Não são papel
da tela de Modelos**: o ajuste da casa delas mora em `nt_modelos` e continua
lá (Notas → Modelos de atos). A base as carrega com o resto;
`modelos_da_casa.minuta_de_fabrica(codigo)` lê uma, e `notas_modelos.minutas()`
devolve a lista inteira (o que é do código — tipo, CENSEC, requisitos,
fundamentação — mais o nome e o corpo da base). A subida (`instalar`) semeia
`nt_modelos` com o texto da base e só atualiza a linha que ninguém editou.

## Como acrescentar um papel (passo a passo para LF06B em diante)

Para cada linha do inventário da sua seção:

1. **O ouro, ANTES de mexer.** Grave em `tests/fixtures/modelos_ouro/` o texto
   e o papel montado com um contexto de teste — **sem dado real de pessoa**
   (LGPD): nomes «DE EXEMPLO», CPF de teste. O modelo é
   `tests/fixtures/modelos_ouro/ouro_lf06a.py`: um `chamadas()` com os
   montadores puros e um `gerar()` que só roda na árvore de antes. Grave o
   commit de antes no próprio fixture. Montador com regra: uma chamada por
   ramo (singular × plural, com e sem selo…) — o `ouro_lf06d.py` tem 217; e o
   texto que mora DENTRO de uma rota se lê do código-fonte de antes pela árvore
   sintática (`_rotas_do_codigo`).
2. **O texto para a pasta, com os mesmos bytes.** Escreva o `.txt` por
   programa, a partir do valor que o código monta hoje
   (`Path(...).write_bytes(texto.encode("utf-8"))`) — copiar e colar no editor
   perde a barra de continuação, troca aspas e acrescenta a quebra do fim.
3. **A ficha** `<CHAVE>.json` (ver acima). Chave em maiúsculas, prefixo da
   atribuição (`RI_`, `RC_`, `NOTAS_`, `PT_`, `RCPJ_`/`RTD_`, `CAIXA_`).
4. **O catálogo** — o papel aparece na tela de Modelos e fica editável:
   - uma linha em `modelos_papeis/<pasta>.py`:
     `{'chave': 'X', 'padrao': ('modulo', 'NOME_ANTIGO')}` (mais `miolo` ou
     `elementos_comuns`, se for o caso). Sem nome antigo, dê ao texto um nome
     que AINDA NÃO EXISTA no módulo (`usucapiao.MODELO_DECISAO_PROCEDENTE`) e
     acrescente o `__getattr__`: o nome de uma função que existe quebra
     `test_o_texto_saiu_mesmo_do_codigo`, que exige o nome fora do módulo — o
     par só serve ao `__getattr__`;
   - o tipo em `modelos_papeis/tipagem.py` (`TIPOS_POR_CHAVE`) — o
     `test_modelos_tipagem_fase0` exige;
   - a contagem em `test_o_catalogo_lista_os_papeis_das_atribuicoes`, com a
     frase de por que o papel entrou;
   - a chave tem de aparecer entre aspas em algum `.py` fora de `tests/`
     (`test_todo_papel_do_catalogo_e_consultado_por_alguma_tela`) — o módulo
     que a lê.
   - **Pasta nova de uma atribuição que já existe** — foi o caso da
     retificação e da usucapião (LF06G), que são procedimentos DO Registro de
     Imóveis, e não atribuições: módulo novo em `modelos_papeis/` com `PASTA`
     própria e `ATRIBUICAO = "Registro de Imóveis"`, a linha dele em
     `modelos_papeis/__init__.py` **logo depois da atribuição** (a tela agrupa
     pela ordem do catálogo; no fim, a atribuição apareceria duas vezes), e
     `elementos_comuns: False` quando o formato do papel não é o da
     atribuição (`CHAVES` no meio do Jinja do RI) — o encerramento comum
     sairia escrito no papel.
   - **papel em Jinja que use claro além de `hoje`, `agora` e `sv` precisa de
     conferidor próprio**, senão a tela recusa todo ajuste (o boneco da
     conferência não tem `t`, `e`, `c`…) — e quem grava (`modelos_elementos.
     salvar`) confere de novo. Registre a conferência pela montagem da
     emissão, com um caso de exemplo, nos dois: `app.extensions[
     "conferidores_de_modelo"]` e `modelos_elementos.CONFERIDORES` (LF06F:
     `rg_web.registrar_rotas`, `wa_web.registrar_rotas`). Papel em chaves
     também ganha com isso: o boneco aprova um `{inventado}`.
   - papel em Jinja numa atribuição em chaves (ou o contrário) leva
     `'elementos_comuns': False`, senão o encerramento comum da atribuição
     estoura (`formato_da_atribuicao`).
   - **papel em HTML que abre no navegador** (era template; ex. a nota e as
     etiquetas do RCPJ/RTD): o AJUSTE da casa passa pelo `html_sem_script`
     antes de ir à página — a tela de Modelos grava com o papel USER, e um
     `<script>` no modelo rodaria na sessão de quem imprime. O padrão sai como
     saía (LF06F: `rg_web.papel_html`).
   - **Atribuição nova de verdade**: pasta nova, módulo novo em
     `modelos_papeis/` com `PASTA` e `ATRIBUICAO`, a linha dele em
     `modelos_papeis/__init__.py`, e a atribuição em `modelos_elementos_schema`
     (`ATRIBUICOES`, `NOME_DA_ATRIBUICAO`, `CHAVE_DO_ROTULO`) e as rotas do
     submódulo em `modelos_elementos_web` — sem isso a tela de Modelos estoura
     ao listar o papel.
   - **Papel `CHAVES`**: registre o conferidor do módulo em
     `app.extensions["conferidores_de_modelo"]` (ver `usucapiao_web`) — sem
     ele a tela confere em Jinja, que aprova `{claro_inventado}` como texto.
5. **O módulo lê pela busca única.** Com `con`: `MODELOS.texto_do_papel(con,
   CHAVE)`. Sem `con`, no caminho «sem modelo → padrão»:
   `MODELOS.padrao_de(CHAVE)`. Tire a constante do módulo. Se alguém de fora
   importa o nome antigo, acrescente o `__getattr__` (copie de qualquer um dos
   catorze módulos do LF06A, ex.: `caixa_web.py`). Nada de leitura da base na
   hora do `import`.
6. **A regra fica no código; a frase vai como peça.** Texto expedido e
   congelado (notificação, termo lavrado) não muda: o que já foi gravado no
   livro continua como está.
7. **O papel montado depois tem de ser IDÊNTICO ao ouro**, byte a byte — o
   teste compara. Prove que o teste pega: troque um byte do `.txt` e veja o
   teste ficar vermelho.
8. **Marque a linha do inventário** com ✓ e a chave que o papel ganhou.
9. Rode os testes do lote, `tests/test_modelos_da_casa.py` (os guardas da
   pasta e da ficha), `tests/test_modelos_tipagem_fase0.py`,
   `tests/test_modelos_elementos.py` e os do módulo tocado.

## O Registro Civil (LF06C) — `rc_textos.py`

Os papéis do civil leem pelo `rc_textos`, que é a regra acima numa função só:

| função | para quê |
|---|---|
| `texto(chave, con=None)` | com `con`, a busca única; sem, o padrão da base |
| `peca(chave, con=None, **claros)` | o texto da peça com os claros (`str.format`) |
| `lendo_da_casa(con)` | enquanto aberto, `texto()` sem `con` lê pela busca única |
| `conferir_claros(chave, corpo)` | o conferidor da tela: o ajuste só usa os claros do padrão |

- **O papel do catálogo é lido onde há conexão** e entra no montador puro
  como `modelo=` (o padrão do `protesto_termo.montar`); sem `modelo`, o
  montador cai no padrão da base.
- **As peças são lidas no fundo de montadores puros, e é por isso que
  `lendo_da_casa` existe.** A qualificação e as frases do termo são lidas dez
  chamadas abaixo de quem tem a conexão. Em vez de pendurar a conexão na
  assinatura de uma dúzia de funções que os testes e o motor de prévia também
  chamam, quem tem a conexão abre `lendo_da_casa(con)` em volta da montagem:
  `rc_termo.montar_para_conferir` (a lavratura), `rc_certidao.emitir` (o teor
  que congela), a tela da averbação de retificação e a prévia da certidão de
  inteiro teor. Fora dele — a prévia do motor, a impressão que monta fora da
  conexão — vale o padrão da base.
- **Papel do civil novo tem conferidor de claros** (`CLAROS_FECHADOS`,
  registrado em `atribuicoes_web`): a conferência geral da tela só pega a
  forma, e um `{claro_inventado}` estouraria `KeyError` na hora de emitir.
  A régua é a de `modelos_da_casa.conferir_claros` (LF06G); o `rc_textos` só
  dá a lista dos claros, que são os do padrão do papel.
- **Não herda o encerramento e o rodapé comuns** (`'elementos_comuns':
  False`): os da atribuição são os dos termos.
- O ouro é um por grupo de módulos: `tests/fixtures/modelos_ouro/ouro_lf06c.py`
  (`gerar <grupo> <raiz-de-antes>` / `conferir <grupo> <raiz>`).

## Onde está no código

- `modelos_papeis/pasta.py` — a leitura da pasta (só arquivo; não toca banco).
- `modelos_papeis/__init__.py` — o catálogo, com a ficha lida da pasta.
- `modelos_da_casa.py` — a base (`carregar_base`, `schema_da_base`), a busca
  (`texto_do_papel`, `padrao_de`), o legado e o aviso de padrão mudado.
- `ri_schema.py` — a subida chama a carga; `mo_modelos.base_impressao`.
- `modelos_elementos_schema.py` / `modelos_elementos.py` — `mo_elementos.base_impressao`.
- `modelos_web.py`, `templates/modelos.html` — o aviso e a diferença na tela.
- `tests/test_modelos_da_casa.py` — o ouro e os guardas.
- `rc_textos.py` — a leitura e o conferidor dos papéis do Registro Civil (LF06C).
- Empacotamento: o `.cgu` (`tools/criar_atualizacao.py`) leva a pasta inteira;
  o público (`tools/exportar_publico.py`) a tem em `PASTAS`.

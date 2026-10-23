# Roteiro para aplicar a versão 3.6.13

Substitui os roteiros da 3.6.0 à 3.6.12, que ficam como registro do que cada um
trazia. **O sistema está suspenso desde 18/08/2026** — nada disto foi aplicado
no servidor, e nada se aplica sem você decidir.

---

## O que esta versão traz

**A certidão do Registro Civil, no modelo nacional do CNJ.** Era o item que
você separou "para uma passada própria" em 25/08, e o último grande buraco das
seis atribuições.

| O que | Onde |
|---|---|
| **Emitir a certidão** | na ficha do assento — Registro Civil → um assento → *Certidão* |
| **Achar quem pede** | *Demais atribuições → Registro Civil — certidões* |
| **A certidão pronta** | com o teor congelado, o `.odt` e o cancelamento |
| **A filiação e a avoenga** | na ficha do assento, num bloco próprio |

Mais três coisas que construí-la trouxe junto:

1. **A carga passou a trazer os pais e os avós** — 1.084 pessoas do acervo, em
   duas tabelas que ela nunca tinha aberto.
2. **A carga passou a lavrar o ato de registro** do assento, com o livro e a
   folha do livro de papel. Sem ele a certidão dizia `LIVRO ND`.
3. **Os pais e os avós entram na conferência de fraude.** Registro de nascimento
   falso se faz com a filiação de outra pessoa, e até agora só o nome do
   registrado era conferido.

---

## Os três casamentos do livro duvidoso — como você decidiu

Construir a certidão achou que o acervo separa os casamentos em dois grupos, e
que o segundo tem **numeração própria em livro próprio** — 3 casamentos, Livro
1, registros 26 a 59, contra 111 a 1.011 em sete livros no primeiro. Isso é o
que costuma distinguir o **B-Auxiliar** (casamento religioso com efeito civil)
do B.

Você respondeu duas coisas, e as duas estão nesta versão:

**"Não tivemos casamentos no livro B-Auxiliar nos últimos anos."** Isso tirou a
urgência: o contador que falta no B-Auxiliar não segura nenhum ato próximo. E
bate com o que está no acervo — os três são de **1979, 1982 e 1987**.

**"Deixe como o E-Ofício guardou, pendente de confirmação quando forem
consultados efetivamente."** Os três continuam no Livro B. E, para a segunda
metade da frase valer, cada um deles leva um **aviso na própria ficha**, que
aparece no dia em que alguém abrir aquele assento — pode ser daqui a cinco
anos, com outro escrevente no balcão. O aviso está:

- no alto da ficha, com o motivo escrito por extenso;
- ao lado do livro, no quadro do assento (*"— por confirmar"*);
- **antes do botão de emitir certidão**, porque errar o livro só sai caro
  quando vira papel assinado.

Quem for à estante conferir tem onde dizer o que viu: o botão **"Confirmei no
livro de papel"**. Depois disso a ficha passa a mostrar quem conferiu e quando,
e a carga nunca mais pergunta.

**Se um dia quiser conferir os três de uma vez**, é o que está na estante:

| Registro | Livro | Folha | Registrado em |
|---|---|---|---|
| 26 | 1 | 13 | 28/12/1979 |
| 44 | 1 | 23 | 17/11/1982 |
| 59 | 1 | 30 | 04/08/1987 |

---

## Os seis passos

### 1. Parar o serviço

```bat
net stop CartorioGestao
```

### 2. Guardar o banco

```bat
copy "%PROGRAMDATA%\CartorioGestao\cartorio.sqlite3" "%PROGRAMDATA%\CartorioGestao\cartorio-antes-da-3.6.13.sqlite3"
```

**Não pule este passo.** Esta versão acrescenta **duas tabelas**
(`rc_certidoes`, as certidões emitidas, e `rc_pessoas`, os pais e os avós) e
**quatro colunas** em `rc_assentos` (o volume do livro, o aviso do livro por
confirmar, e quem o conferiu e quando). Todas entram sozinhas ao abrir o banco,
e **nenhuma apaga nada**. A cópia é o caminho de volta se algo não parecer
certo.

### 3. Conferir o pacote

O arquivo é `CartorioGestao_3.6.13.cgu`, e a impressão digital SHA-256 dele é:

```
78edeefebb5f7069868e7c9cd3ff20494a2d985155496d4a350a880ddb002723
```

O arquivo tem 1,0 MB. Para conferir no servidor, antes de aplicar:

```bat
certutil -hashfile CartorioGestao_3.6.13.cgu SHA256
```

### 4. Aplicar

```bat
ATUALIZAR_SISTEMA.cmd
```

### 5. Rodar a carga do acervo de novo

Em *Demais atribuições → Carga do acervo*.

**Ela é repetível por construção**: os assentos que já estão no banco voltam
como "repetidos" e não se duplicam. O que ela faz de novo é trazer **os pais, os
avós e o ato de registro** dos 244 assentos que já estavam lá — a passada olha
o que **falta**, e não o que acabou de entrar.

Ao terminar, a tela deve mostrar, nas contagens do Registro Civil:

- `pessoas_de_filiacao: 1084`
- `atos_de_registro: 244`
- `assentos_com_livro_a_confirmar: 3`

**Se algum número vier diferente disso, me diga antes de seguir** — eles saíram
de um ensaio contra uma cópia do acervo desta casa, e diferença quer dizer que
o acervo do servidor não é o que eu medi.

### 6. Responder o que só você sabe

Em *Demais atribuições → O que falta informar*. As pendências abertas hoje:

1. o próximo número do **Registro de Protestos** e do **Registro de Pagamentos**
2. a **letra da posição 566** do retorno da CRA, para apresentante novo — e
   agora são três caminhos aceitos: `A`, `P` e **branco**
3. o **Livro 6 de Apontamento**, aberto em 05/03/2024 e nunca usado
4. o próximo número dos **três livros do RCPN** que o E-Ofício nunca teve —
   B-Auxiliar, C-Auxiliar e D
5. **os três casamentos do livro duvidoso** — já decidida por você: fica como
   está, e a confirmação acontece na ficha de cada um, quando forem consultados

Nenhuma delas trava o balcão hoje. A 1 e a 4 travam o **primeiro ato novo** de
cada série, porque sem elas ele nasceria com o número 1 sobre acervo que já
passou disso — o defeito de 18/08 outra vez. A 4 ficou menos urgente com a sua
resposta sobre o B-Auxiliar: não entra casamento religioso há anos.

---

## Se algo der errado

```bat
net stop CartorioGestao
copy "%PROGRAMDATA%\CartorioGestao\cartorio-antes-da-3.6.13.sqlite3" "%PROGRAMDATA%\CartorioGestao\cartorio.sqlite3"
```

e me diga o que apareceu na tela, com as palavras que estavam escritas nela.

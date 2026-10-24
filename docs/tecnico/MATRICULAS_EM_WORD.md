# Matrículas antigas digitadas em Word — o que fazer

**14/08/2026.** A pasta de rede da serventia terminou de baixar, e com isso a leitura deixou de
depender de um script solto: virou um botão dentro do sistema, em **Matrículas em Word**.

---

## O que já foi lido e conferido

A pasta tem **2.988 arquivos**. Depois de descartar o que não é matrícula e de escolher uma
versão para cada número, sobraram **2.768 matrículas**, todas com o texto extraído — inclusive
os 760 arquivos no formato `.doc` antigo, que passaram pelo LibreOffice.

Comparadas com o acervo (1.700 matrículas, 1.506 com teor):

| Situação | Quantas | O que significa | Entra na carga? |
|---|---:|---|---|
| **Não existem no sistema** | 1.097 | O número não está no acervo | Sim |
| **O Word continua o texto** | 367 | Tudo o que o sistema tem reaparece no arquivo digitado, que segue com o título aquisitivo, o fecho e as averbações | Sim |
| **Existem sem teor** | 191 | A matrícula está no sistema, mas sem texto nenhum | Sim |
| **Textos batem** | 974 | Nada a fazer | Não |
| **Textos se contradizem** | 135 | Os dois lados afirmam coisas incompatíveis | **Não** |
| **Número em dois livros** | 1 | A matrícula 8 existe no Livro 2-A e no Livro 2S | **Não** |
| **Documento sem texto** | 3 | Arquivos marcados "SEM EFEITO" (91, 99 e 641) | Não |

Carregando as três primeiras faixas, o acervo vai de **1.700 para 2.797 matrículas**, e a
cobertura de teor de **89% para praticamente 100%**.

---

## Como rodar

1. Menu **Matrículas em Word**.
2. No campo **Pasta**, o caminho fica gravado depois da primeira vez:
   `C:\caminho\da\pasta\das\matriculas\em\word`
3. **Ler a pasta agora.** Leva cerca de um minuto. Só lê: não altera, não move e não apaga nada
   na origem.
4. Conferir os números na tela e **Trazer as marcadas para o sistema**.

Pode rodar quantas vezes quiser. Se alguém digitar mais matrículas na pasta, é só ler de novo.

---

## O que o sistema decide sozinho, e o que ele não decide

**Decide qual arquivo ler** quando há mais de uma versão do mesmo número — são 172 casos.
A regra, em ordem: "ATUALIZADA" ganha do original; `.docx` ganha de `.doc`; "cópia em conflito"
do sincronismo da nuvem perde; "SEM EFEITO" perde e só entra se for o único. Empatando, vale o
arquivo maior. A tela mostra quantas versões havia e qual foi preterida.

**Não decide nada de registral.** O texto entra na ficha exatamente como estava no Word, sem
interpretação, e **toda matrícula carregada fica marcada como não conferida** — inclusive as
que já estavam conferidas e tiveram o teor ampliado, porque conferência antiga não vale para
texto novo. Isso resolve o acesso à informação, não a fé pública: a conferência contra o livro
físico continua obrigatória, matrícula por matrícula.

**Os 135 que se contradizem ficam esperando você.** A tela mostra os dois textos lado a lado e
para por aí. Em 87 deles o arquivo digitado tem bem mais texto que o sistema; em 23 é o
contrário — nesses últimos, carregar o Word perderia informação.

---

## Duas coisas que apareceram e você precisa saber

**A matrícula 8 está duplicada no acervo**, vinda assim do E-Ofício: uma no Livro 2-A e outra no
Livro 2S. Como cada livro reinicia a numeração, o número sozinho deixou de identificar a
matrícula, e o sistema se recusa a adivinhar qual delas o arquivo `08.docx` atualiza. Vale
conferir no livro e decidir — se forem mesmo duas matrículas distintas, o cadastro precisa
distinguir pelo livro.

**Seis arquivos ficaram de fora por não trazerem número reconhecível:** `MATRICULA OFICIAL.docx`,
`MODELO DE FICHA.docx`, `_ANEXOS.docx`, `_TERMO DE ABERTURA.doc`, `xx.docx` e
`Artigo 26 da Lei nº 8ITBI.docx`. Os cinco últimos parecem mesmo não ser matrícula. O primeiro
talvez seja — vale abrir.

---

## Onde ficou a leitura

O resultado é gravado em `matriculas_doc.jsonl`, dentro da pasta de arquivos do sistema, que o
backup já varre. Ao lado dele fica `matriculas_doc.descartados.json`, com a lista dos nomes que
o sistema não conseguiu ler e o motivo de cada um.

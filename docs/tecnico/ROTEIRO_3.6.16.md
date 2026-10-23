# Roteiro para aplicar a versão 3.6.16

A 3.6.15 você aplicou em 27/08/2026, às 08h41. Esta é a de cima dela, do mesmo
dia. Os roteiros anteriores ficam como registro do que cada um trazia.

---

## O que esta versão traz

### 1. Cada atribuição no seu próprio lugar

Acabou o item «Demais atribuições». O Registro Civil desta casa aparecia como
*demais*, ao lado do Protesto, e quem trabalha no balcão do civil abria um menu
que não tinha o nome do que ele faz.

Agora o menu é:

| Grupo | O que tem dentro |
|---|---|
| **Tabelionato de Notas** | como estava |
| **Registro de Imóveis** | como estava, **mais o Registro Auxiliar — Livro 3** |
| **Protesto** | Títulos · Certidões · Remessa da CRA · Avisos e editais · Desistências · Retorno à CRA |
| **Registro Civil** | Assentos · Certidões |
| **RCPJ e RTD** | **RCPJ** · **RTD** (agora cada um com a sua lista) · Certidões de inteiro teor |
| **Livros e acervo** | Livros e termos · Encerramento diário · Numeração · O que falta informar · Trazer o acervo |

**O Livro 3 mudou de lugar** porque é o que ele é: o Registro Auxiliar **do**
Registro de Imóveis — a numeração dele já saía do contador do RI. Estava fora do
módulo de que faz parte.

**O RCPJ e o RTD ganharam cada um a sua lista.** Quem procura um contrato de
aluguel não vê mais sociedade civil no meio. A tabela continua sendo uma só,
porque o acervo do E-Ofício já os guardava juntos e o livro tem a mesma forma
nos dois — o que se separou foi o que o balcão vê.

Dois defeitos caíram junto: **o núcleo não tinha grupo** (os links ficavam em
«Demais atribuições» e a página abria o «Administrativo» — o menu se fechava em
cima de quem o usava), e a **ajuda perdia os links de menu com filtro**.

### 2. O selo sai quando o ato é praticado

Como você pediu, e como o E-Ofício fazia.

**O que estava errado não era só a configuração.** O caminho do selo automático
estava pronto e testado neste sistema desde o começo — e **nenhuma tela o
chamava**. A única forma de selar era o escrevente digitar o número à mão.

Agora, no Registro Civil, o selo é pedido ao aparelho assim que o ato é lavrado:
no assento novo, na averbação, na anotação, na retificação.

**Se o aparelho não responder, o ato não cai.** Ele é lavrado sem selo, a tela
diz isso na mesma frase (*"o ato foi lavrado SEM SELO: …"*) e ele aparece na
lista de atos sem selo. Balcão parado é pior que selo atrasado.

**O selo digitado à mão continua existindo** — e quando alguém digita um, o
sistema não pede outro. Dois selos para o mesmo ato é dinheiro da serventia
saindo duas vezes.

---

## O que você precisa fazer para o selo funcionar

**O selador nunca foi configurado neste sistema.** Conferi em 27/08: a
configuração está vazia e a senha não foi informada. Enquanto isso não for
feito, nenhum ato sai selado — e o sistema nem tenta, então ninguém espera.

Conferi também o que já está pronto do seu lado:

- o aparelho em `192.0.2.23` está **ligado e respondendo**;
- a impressão digital do certificado dele é a mesma que está documentada;
- **usuário, senha e endereço estão dentro do acervo do E-Ofício** — dá para
  importar sem ninguém digitar senha.

Em *Administrativo → Selador — configuração*, na ordem:

1. **Importar do E-Ofício** — traz endereço, usuário e senha.
2. **Ver o certificado** — vai mostrar `3AB:FB:96:…`.
3. **Fixar o certificado** — a partir daí só aquele aparelho serve.
4. **Testar** — autentica e grava o resultado na tela.

---

## Uma coisa que ainda sai sem selo, e é medição que falta

**A certidão do Registro Civil.** A casa selou certidão do civil por **sete
caminhos diferentes**, e qual deles vale para cada certidão ainda não foi
medido:

| Selos | Caminho |
|---:|---|
| 122 | `/selo/civil/nascimento/segunda-via` |
| 28 | `/selo/civil/nascimento` |
| 15 | `/selo/civil/casamento/segunda-via` |
| 8 | `/selo/civil/obito` |
| 1 | `/selo/civil/nascimento/transcricao/segunda-via` |
| 1 | `/selo/civil/obito/segunda-via` |

Repare que **casamento só aparece em segunda via** — não existe
`/selo/civil/casamento` nos selos que esta casa emitiu. Isso é o tipo de coisa
que não se adivinha: escolher um caminho por semelhança seria selar por onde
ninguém selou. Até medir, a certidão sai sem selo e a tela diz por quê.

---

## Os quatro passos

### 1. Parar o serviço

```bat
net stop CartorioGestao
```

### 2. Guardar o banco

```bat
copy "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3" "%PROGRAMDATA%\CartorioGestao\cartorio_gestao-antes-da-3.6.16.sqlite3"
```

**Esta versão não acrescenta nem tira nenhuma tabela e nenhuma coluna** — só
código e telas. Ainda assim, a cópia é o caminho de volta em trinta segundos.

### 3. Conferir e aplicar

O arquivo é `CartorioGestao_3.6.16.cgu`, 1,1 MB, e a impressão digital SHA-256
dele é:

```
514d2f88047e6def25f67707f0f3f2448fd666afffe0f425669af44192838fbb
```

```bat
certutil -hashfile CartorioGestao_3.6.16.cgu SHA256
ATUALIZAR_SISTEMA.cmd
```

> **O `ATUALIZAR_SISTEMA.cmd` mudou nesta rodada**: ele passou a copiar o
> `VERSAO.txt` e a carimbar o `install.json`. Até 27/08 ele copiava só o código,
> e os dois arquivos continuavam dizendo **3.2.1** com a 3.6.15 no ar. Depois de
> aplicar, os dois devem dizer **3.6.16**.

### 4. Rodar a carga do acervo

**Isto continua pendente da 3.6.15**, e é o que importa mais: em
*Livros e acervo → Trazer o acervo do E-Ofício*.

As quatro atribuições estão de pé e **vazias**, e nenhum contador foi semeado —
o primeiro ato novo de cada série nasceria com o número 1 sobre acervo que já
passou disso. Ao terminar, as contagens do Registro Civil têm de mostrar
`pessoas_de_filiacao: 1084`, `atos_de_registro: 244` e
`assentos_com_livro_a_confirmar: 3`. **Número diferente disso, pare e me diga.**

---

## Se algo der errado

```bat
net stop CartorioGestao
copy "%PROGRAMDATA%\CartorioGestao\cartorio_gestao-antes-da-3.6.16.sqlite3" "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3"
```

e me diga o que apareceu na tela, com as palavras que estavam escritas nela.

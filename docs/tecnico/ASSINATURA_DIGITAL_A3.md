# A assinatura digital do delegatário — a estratégia, e o que a decidiu

Decisão do oficial em **01/09/2026**: *«certificado é A3 do delegatário. Vamos
construir essa ferramenta, ela vai ser útil em muitos módulos.»*

Ela nasceu de uma pergunta dele — *«onde emitir o instrumento eletrônico do
protesto?»* — e da pasta que ele subiu logo depois: **seis instrumentos de
protesto assinados**, cada um um `.pdf` com um `.p7s` ao lado.

> **Eles são de Carira/SE**, do acervo que ele trouxe em 26/08, e não desta
> casa. Vale a regra que este projeto já tem escrita: **layout, sim;
> convenção, não.** A forma do documento assinado é nacional; a Lei estadual e
> o Selo TJSE que aparecem no papel são de lá.

---

## O fato que decide a arquitetura

**Carregar o driver PKCS#11 do token DERRUBA O PROCESSO.** Medido nesta
máquina, nos dois drivers instalados:

```
eTPKCS11.dll         -> Segmentation fault, código de saída 139
IDPrimePKCS1164.dll  -> Segmentation fault, código de saída 139
```

E ele acontece **no `load`**, antes de qualquer saída — não é exceção, é
segfault. **Segfault não se trata com `try/except`**: ele mata o processo.

> **Se o Flask carregasse esse driver, o waitress morreria e o balcão inteiro
> sairia do ar** — não uma tela: o sistema. Isto não é risco projetado, é o que
> aconteceu nas duas vezes em que se tentou.

Isso, somado ao que o A3 é por definição — **a chave privada não sai do
token** —, fecha o desenho:

**A ASSINATURA ACONTECE FORA DO PROCESSO DO SISTEMA. Sempre.**

---

## O que o sistema faz, e o que ele nunca faz

| faz | nunca faz |
|---|---|
| monta o documento | assina |
| guarda o que voltou assinado | guarda a chave |
| **confere** se o assinado é o que ele emitiu | guarda o PIN |
| lê **quem** assinou | carrega driver de token |

**Ele não tem função que assine, e isso se varre** — como já se faz na ajuda
(que não lavra), no usucapião (que não decide) e na lista de fraudes (que não
recusa). Aqui a razão é mais dura ainda: **ele não pode assinar mesmo que
quisesse.**

---

## O que dá para conferir SEM a chave — medido no `.p7s` real

Com `asn1crypto`, que já está no runtime, e sem nenhum segredo:

| | medido no instrumento de 09/06/2025 |
|---|---|
| é PKCS#7 `signedData`? | **sim** |
| o documento vem **dentro** do `.p7s`? | **sim** — 81.937 bytes, byte a byte iguais ao PDF |
| quem assinou | `PESSOA EXEMPLO:00000000191` — nome e CPF, do e-CPF |
| a cadeia | AC SOLUTI Multipla v5 → AC SOLUTI v5 → Raiz Brasileira v5 |
| algoritmo | `rsassa_pkcs1v15`, digest **sha1** |

**A conferência que mais protege é a segunda**, e ela não precisa de
criptografia nenhuma: **o documento embrulhado tem de ser byte a byte o que a
casa emitiu.** É ela que pega o caso real — assinar o arquivo errado, ou o
arquivo alterado depois de gerado.

> **A assinatura é ANEXADA, e não destacada.** O `.p7s` tem 87.888 bytes e o
> PDF tem 81.937: o PDF começa no **byte 68** dele, e a firma ocupa os 5.951
> restantes. **O PDF sozinho não tem assinatura embutida** — quem guardar só o
> PDF guardou um papel sem firma.

---

## Os dois caminhos para a assinatura entrar

### 1. O delegatário assina no assinador dele e devolve o arquivo

**É o que funciona hoje, sem integração nenhuma.** O sistema gera o PDF, ele
assina com o programa que já usa para o token, e sobe o `.p7s`. O sistema
confere os quatro itens acima e arquiva.

Vantagens que não são pequenas: **não depende de o token estar na máquina do
servidor**, não pede PIN a ninguém pelo navegador, e **não carrega driver
nenhum** — logo não derruba o balcão.

### 2. Um ajudante à parte, se um dia o driver parar de estourar

Um processo **separado** que carrega o driver, pede o PIN e devolve o `.p7s`.
Mesmo funcionando, ele fica em processo próprio pela razão de sempre: um
segfault ali mata o ajudante, e não o servidor.

**Não se constrói hoje**, e o motivo está medido acima. Fica declarado aqui
para não ser reinventado por engano.

---

## Por que isto serve muitos módulos

O oficial disse que serviria, e serve: **o que muda de um papel para outro é o
documento, e não a assinatura.** A fila é a mesma —

```
o módulo monta o papel  ->  espera assinatura  ->  volta assinado  ->  arquivado
```

— e cada módulo entra nela dizendo só **de que ato aquele papel é**. Hoje o
sistema emite nove papéis (certidões do RI, do RCPN, do RCPJ/RTD e do Livro 3,
termos de livro, recibos, traslados, comprovante de prenotação, editais), e o
instrumento de protesto é o décimo.

**Por isso o módulo não é `protesto_alguma_coisa`.** Ele é do núcleo, como o
`ato_selado` e o `livro_nucleo` — pela mesma razão de sempre: escrever a
mesma coisa em dez lugares produz dez versões divergentes do pedaço que
responde «este papel está assinado?».

---

## O que fica esperando decisão

**Quem pode assinar.** O certificado é **do delegatário**, e não da serventia:
o CPF dentro dele é o de uma pessoa. Se um substituto puder assinar, é outro
certificado e outro CPF — e o sistema tem de saber os dois, senão recusará o
papel legítimo do substituto.

**O que fazer com papel não assinado.** A regra que este projeto já usa para o
selo é a resposta natural: **o papel sai, e diz que está sem assinatura**.
Papel que se afirma assinado sem estar é pior que papel sem assinatura — e é o
«carimbo que mente» na sua forma mais cara.

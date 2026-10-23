# Roteiro da 3.6.61 — o Protesto sai de vista, e a assinatura do delegatário entra

**O que esta versão faz de mais importante, em uma frase:** ela **desliga o
módulo de Protesto** para o balcão, como você mandou, e entrega pronta a
ferramenta de **assinatura digital** que vai servir os outros módulos.

---

## 1. O Protesto está desligado — e o caminho de volta está pronto

Sua ordem: *«vamos desabilitar o modulo de protesto para os usuarios, protesto
vai ficar para um futuro»*.

**O que acontece quando você aplicar esta versão:**

| | |
|---|---|
| o grupo **Protesto** | **some do menu** |
| quem tiver o endereço nos favoritos | **não entra** — a tela recusa e diz por quê |
| os 1.366 títulos, 1.160 protestos, 56 cancelamentos e os selos | **continuam no banco, intactos** |
| as certidões de protesto já emitidas | continuam guardadas |

**Desligar módulo nunca apaga ato.** Ato lavrado é livro, e livro não se fecha
porque a tela saiu do menu.

### Por que é uma chave, e não uma amputação

Você escreveu *«fica para um futuro»* — e futuro quer dizer que ele volta.
Se eu tivesse apagado o menu e as rotas no código, **o retorno custaria uma
versão nova, empacotada e aplicada**. Do jeito que ficou, você religa sozinho:

> **Administrativo → Configurações → «Módulo de Protesto ligado»**

Marque a caixa, salve, e o grupo volta ao menu com tudo no lugar. Há teste que
prova os dois lados — desligado não abre, religado volta.

### O que continua aparecendo, e é de propósito

Em **O que falta informar** seguem as duas pendências de numeração do Protesto
(o próximo número do Registro de Protestos e o do Registro de Pagamentos).
**Elas não saíram da lista porque continuam sendo verdade** — e quando o
módulo voltar, elas são a primeira coisa que ele vai precisar. Pendência se
apaga quando é resolvida, e não quando a tela sai do menu.

---

## 2. A assinatura digital do delegatário — a ferramenta que serve muitos módulos

Sua ordem: *«certificado é A3 do delegatário. Vamos construir essa ferramenta,
ela vai ser útil em muitos módulos. Documentar a estratégia no roteiro»*.

### O fato que decidiu a arquitetura, e ele é medido

**Carregar o driver do token nesta máquina DERRUBA O PROCESSO.** Testado nos
dois drivers instalados:

```
eTPKCS11.dll         -> Segmentation fault, código de saída 139
IDPrimePKCS1164.dll  -> Segmentation fault, código de saída 139
```

E acontece **no carregamento**, antes de qualquer coisa. Isso não é erro que
se possa tratar: mata o processo inteiro. **Se o sistema carregasse esse
driver, o servidor morreria e o balcão inteiro sairia do ar** — não uma tela:
o sistema.

Somado ao que o A3 é por definição — a chave privada não sai do token —, o
desenho está fechado:

> **A assinatura acontece FORA do sistema. Sempre.**
> Você assina no assinador que já usa, e sobe o `.p7s`.

### O que o sistema confere sem chave nenhuma

Medido nos **seis instrumentos assinados** que você subiu:

| | resultado |
|---|---|
| é assinatura PKCS#7 de verdade? | **sim, nos 6** |
| o documento vem **dentro** do arquivo assinado? | **sim** — byte a byte igual ao PDF |
| quem assinou | **PESSOA EXEMPLO, CPF 00000000191** — nos 6 |

**A conferência que mais protege é a do meio, e ela não precisa de
criptografia:** o documento embrulhado tem de ser byte a byte o que a casa
emitiu. É ela que pega o caso real — assinar o arquivo errado, ou o papel
alterado depois de gerado.

### O que ele NÃO afirma, e diz que não

**Não diz «assinatura válida».** Conferir isso exige as âncoras de confiança
da ICP-Brasil e a lista de revogação, que esta casa não tem. Dizer «válida»
sem ter conferido seria o carimbo que mente na forma mais cara — num papel que
a serventia põe no mundo. Quem valida a firma é o validador oficial.

**E o módulo não tem função que assine** — há teste que varre os nomes
procurando `assinar`, `token`, `pin`, `chave_privada`.

### Duas coisas esperam decisão sua

1. **Quem mais pode assinar.** O certificado é **do delegatário**: o CPF
   dentro dele é de uma pessoa. Se o substituto puder assinar, é outro
   certificado e outro CPF — e o sistema precisa saber os dois, senão vai
   recusar o papel legítimo dele.
2. **Confirmar que papel não assinado sai dizendo que está sem assinatura**
   — é a regra que a casa já usa para o selo, e eu a apliquei por analogia.

---

## 3. O instrumento de protesto — construído, e entra desligado junto

Sua pergunta de hoje: *«onde emitir o instrumento eletrônico do protesto?»* —
e a resposta era **em lugar nenhum**. O sistema lavrava o protesto, escrevia o
termo no livro, e parava ali; o art. 20 da Lei 9.492/1997 manda entregar o
instrumento ao apresentante.

Ele ficou pronto e **entra no pacote desligado com o resto do Protesto** —
você mandou empacotar do jeito que está, e é o que foi feito. Quando o módulo
voltar, ele está lá.

**Não há precedente de forma nesta casa**: procurei nas 229 tabelas do
E-Ofício e não há uma sequer com «instrumento» no nome. Onde não há forma a
imitar, o que se imita é a lei — e o texto foi para o **catálogo de modelos**,
que é seu para editar.

### Os dez itens do art. 22, e os dois que esta casa não tem

O sistema confere item a item antes de você assinar. Dois não fecham, e os
dois estão **declarados, e não escondidos**:

- **Item II — endereço do apresentante.** Medido: o arquivo da CRA, por onde
  entram 93% dos títulos, traz o **código e o nome** do apresentante e
  **nenhuma posição de endereço**; e o acervo não tem cadastro dele
  (`tbCedente` é o **cedente**, que é outro papel e que já temos). Não
  inventei e não calei: aparece na conferência, com o motivo.
- **Itens V e VI** — intervenientes voluntários e aceite por honra. Só cabem
  em letra de câmbio; ficam marcados como «não se aplica», para quem for
  procurar não achar que foram esquecidos.

### O § único é uma dispensa condicional, e a condição se mede

A lei dispensa transcrever o título **se a serventia conservar cópia** — e
manda **dizer isso expressamente** no instrumento. São duas obrigações, e não
uma. O sistema pergunta ao banco se há imagem arquivada daquele título: se
há, escreve a menção; **se não há, o papel diz que a dispensa não se aplica**.
Escrever a menção sem ter a cópia seria afirmar um arquivo que ninguém
conferiu.

---

## 4. A chave do CENPROT confirmada por um caso que a nossa casa não tinha

Os seis instrumentos que você subiu são de Carira/SE, e **o nome de cada
arquivo é a chave de 23 dígitos do CENPROT**. Isso permitiu conferir a leitura
que fizemos ontem contra um caso que os nossos 175 títulos não separavam:

| | |
|---|---|
| data do protocolo | **09/06/2025** |
| data em que o protesto foi lavrado | **13/06/2025** |
| o que a chave carrega | **250609** — a do **protocolo** |

Nos nossos 175 as duas datas coincidiam, e por isso nunca decidiam.
**Um caso que separa vale mais que cinco que concordam** — e agora está
confirmado em 6 de 6, noutra serventia e noutro estado.

---

## 5. Dois achados que **não** são desta noite, e que ficam abertos

A suíte inteira só roda quando você pede — sua ordem de 31/08. A última vez
tinha sido na **3.6.51**, e desde então saíram oito versões. Ao rodá-la agora,
o varredor de «função pronta que nenhuma tela chama» — o defeito que mais se
repetiu neste projeto — acusou **75 funções órfãs contra 63 na 3.6.51**.

Doze nasceram nesse intervalo. **Dez são auxiliares legítimas** (várias do
Protesto, que está desligado, e da assinatura, cuja tela é o próximo passo).
**Duas parecem defeito**, e eu não as consertei porque não são o que você
pediu hoje — mas elas não podem ficar sem registro:

### O primeiro é o mais sério, e é sobre a ajuda

`ajuda_web.py` traz escrito, em comentário, que a tela de pré-visualização
usa *«as mesmas funções da consulta — `montar_envio`, `montar_instrucao` e
`o_que_sai` —, e não uma cópia parecida, que divergiria no primeiro
conserto»*. **O varredor diz que ninguém as chama.**

Ou o comentário está mentindo, ou a prévia foi reescrita por fora em algum
momento. Nos dois casos é exatamente o defeito que aquelas funções existiam
para impedir: **a tela mostrar uma coisa e o sistema mandar outra** — e o que
sai numa consulta da ajuda é dado de cliente.

**Não é urgente para o balcão** (a ajuda funciona), mas é para o sigilo, e
entra na próxima se você concordar.

### O segundo é menor

`rc_certidao_odt.html_odt_da_certidao` faz `return ""` — devolve texto vazio
— e é a **última função de um arquivo de 287 linhas**. Tem cara de coisa
interrompida no meio. Ninguém a chama, então não estraga nada hoje.

### E há uma lição de cadência aqui, que é sua para decidir

Acumular entregas antes de empacotar economizou muitas horas de suíte — a
medição que justificou sua ordem continua valendo. **O preço, agora medido:
o que só a suíte inteira pega ficou oito versões escondido.** Uma saída
intermediária, se você quiser: rodar só os varredores (são segundos, não
meia hora) a cada entrega, e a suíte inteira quando você pedir. Fica a
critério seu; eu sigo a ordem que você der.

---

## 6. Como conferir que subiu certo

Depois de aplicar, abra o sistema e confira estas quatro coisas:

| o que olhar | o que tem de aparecer |
|---|---|
| o menu | **sem o grupo Protesto** |
| digitar `/protesto` no endereço | aviso amarelo dizendo que o módulo está desligado |
| Administrativo → Configurações | a caixa **«Módulo de Protesto ligado»**, desmarcada |
| Ajuda → versão | **3.6.61** |

Se o grupo Protesto ainda aparecer no menu, **a atualização não subiu** —
rode o `ATUALIZAR_SISTEMA.cmd` de novo e confira o `VERSAO.txt`.

---

## 7. O que não mudou

- Nenhum dado foi apagado, movido ou reescrito.
- Nenhuma outra atribuição foi tocada: Notas, RI, RCPN, RCPJ/RTD, Livro 3,
  caixa, malote e núcleo seguem iguais.
- O banco ganha **duas tabelas novas** e nada mais: `as_documentos` (a fila de
  assinatura da casa) e `pt_instrumentos`. As duas nascem vazias.

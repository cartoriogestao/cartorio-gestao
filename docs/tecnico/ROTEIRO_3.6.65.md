# ROTEIRO DA 3.6.65 — a resposta ao relato #41

Empacotada em **02/09/2026**, poucas horas depois da 3.6.64. **Ela existe por
causa de um relato seu**, e traz duas coisas: um conserto que vale 48 segundos
por certidão, e outro que vale para 99 telas.

Substitui a 3.6.64; **basta esta** — exige a 3.3.0 como mínimo.

---

## O PACOTE

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.65.cgu` |
| SHA-256 | `42a87cd4141875f01c55532c129d5fab9f8a7150c03209d0247076e40a789981` |
| tamanho | 2.930.537 bytes · 546 arquivos |
| exige no mínimo | 3.3.0 |

**Conferido byte a byte contra a árvore que a suíte testou**: 546 de 546
iguais, zero diferentes, zero sobrando, nenhum cache de ferramenta.

**A suíte inteira rodou antes de empacotar**: **4.337 testes passando, 6
pulados, zero falhas**, em 32m33s. São 16 a mais que a 3.6.64 — os onze da
impressora e os cinco do cabeçalho.

---

## O QUE VOCÊ RELATOU

> «página de certidões quando clica em imprimir pdf fica carregando muito tempo
> e fica aparecendo umas letras estranhas no fundo» — relato #41, 21h23

São **duas coisas**, e elas têm causas diferentes.

---

## 1. A DEMORA — resolvida, e a causa está medida

**Era uma impressora gravada dentro do molde.**

Todo arquivo `.odt` guarda, no `settings.xml`, a impressora de quem o salvou.
O molde da certidão carrega a sua — a `EPSON344007 (L4260 Series)`. Ao abrir o
documento para converter em PDF, o LibreOffice pergunta as capacidades dela; e
**quando ela não está alcançável na rede, ele espera o tempo limite**.

Medido contra o molde real:

| | tempo | PDF que sai |
|---|---|---|
| molde como está | **50,6 s** | 132.469 bytes |
| molde sem a impressora | **2,6 s** | 132.469 bytes |

**Vinte vezes mais rápido, e o papel é o mesmo.**

**Isto explica o que estava registrado como inexplicável.** Em 01/09 ficou
escrito que o tempo era «errático» — 1 segundo de manhã, 51 à tarde, mais de 10
minutos num perfil novo. Não era errático: era a impressora estar ligada ou
não. Constante porque era **espera**, e não trabalho.

**A limpeza é na hora de converter, e não no molde.** Se o arquivo fosse limpo
em disco, a impressora voltaria no dia em que você abrisse o molde no
LibreOffice para ajustar o desenho — e você vai. Assim vale para os **sete
papéis** da casa e não depende de ninguém lembrar.

**E o `.odt` que você baixa continua intacto**, com as suas escolhas: o que se
limpa é a cópia que vai ao conversor.

---

## 2. AS LETRAS ESTRANHAS — um defeito achado, e a pergunta que falta

**O seu print resolveu metade e abriu a outra.**

**O texto repetido não vem do sistema.** Medido: o HTML que o servidor manda
para `/rcpn/certidoes` não contém aquele texto em forma nenhuma. Ele nasce no
navegador, ao desenhar a página.

**Mas o print achou um defeito nosso, de verdade.** O CSS mandava o cabeçalho
de **toda** tabela do sistema «grudar» no alto ao rolar — e para grudar ele
precisa de um quadro que role. **Noventa e nove telas não têm esse quadro**:
nelas o cabeçalho apoiava-se **na janela**, flutuava sobre o conteúdo e
disputava lugar com a barra do topo, que também gruda.

Cabeçalho grudado sem quadro é **redesenho a cada passo da rolagem**, que é a
família de defeito que produz arraste de pixels. E o seu print é de uma tela
rolada. Agora ele só gruda dentro do quadro que rola.

> **O QUE EU NÃO AFIRMO: que era isto que você viu.** Não consegui reproduzir
> o artefato. Você acessa por **AnyDesk**, de outro computador — e desktop
> remoto transmite só o pedaço que mudou, o que produz arraste parecido por
> conta própria.

**A pergunta que separa as duas causas, e que só você pode responder:**

> **Acontece também quando você usa o computador do servidor direto, sem
> AnyDesk?**

- Se **acontecer** direto: é do sistema, e o conserto do cabeçalho pode ter
  resolvido — me diga se some.
- Se **só acontecer pelo AnyDesk**: é da transmissão remota, e o caminho é
  outro (desligar a aceleração de hardware do Chrome, ou o modo de qualidade
  do AnyDesk).

---

## COMO APLICAR

1. Feche o sistema no servidor.
2. Rode o `ATUALIZAR_SISTEMA.cmd`.
3. Confira as três coisas abaixo.

O banco não ganha tabela nova nesta versão.

---

## AS TRÊS COISAS PARA CONFERIR

| | o que fazer | o que tem de acontecer |
|---|---|---|
| 1 | *Registro Civil → Certidões* → **Ver** → **Imprimir** | o PDF abre em **poucos segundos**, e não em um minuto |
| 2 | o mesmo PDF | sai **igual** ao de antes — a impressora não muda o papel |
| 3 | rolar qualquer tela com tabela longa | o cabeçalho **não flutua** sobre o conteúdo |

E, se as letras estranhas voltarem: **me diga o que aparece, em que navegador,
e se acontece sem o AnyDesk.**

---

## O QUE MAIS VEIO JUNTO

Tudo o que estava na 3.6.64 — as duas Centrais de Protesto, a senha fora do
banco, o menu do Protesto em três seções e o balcão do WhatsApp. Ver
`ROTEIRO_3.6.64.md`.

# ROTEIRO DA 3.6.64 — o que aplicar, e o que decidir

Empacotada em **02/09/2026**. Substitui a 3.6.62; **basta esta** — o pacote
exige a 3.3.0 como mínimo, como todos os anteriores.

---

## O PACOTE

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.64.cgu` |
| SHA-256 | `618524e323f9b43c72442a8837321331c33a69a46130770be9296215a6ff3213` |
| tamanho | 2.925.077 bytes · 545 arquivos |
| exige no mínimo | 3.3.0 |

**Conferido byte a byte contra a árvore que a suíte testou**: 545 de 545
iguais, zero diferentes, zero sobrando, e **nenhum cache de ferramenta** —
`.pytest_cache/lastfailed` copiado para o balcão diz que testes falharam ali,
e tem cara de resposta.

**A suíte inteira rodou antes de empacotar**, no runtime do próprio servidor:
**4.321 testes passando, 6 pulados, zero falhas**, em 55m24s com
`-n 4 --dist loadfile`. São 182 a mais que a rodada anterior.

---

## COMO APLICAR

1. Feche o sistema no servidor.
2. Rode o `ATUALIZAR_SISTEMA.cmd`.
3. Abra o sistema e confira as **sete coisas** da última seção.

O banco migra sozinho ao subir. **Duas tabelas novas** entram nesta versão:
`cn_pendencias` (o que a CENPROT manda) e as do balcão do WhatsApp. Nenhum
dado antigo é tocado.

---

## O QUE MUDOU, na ordem em que o balcão sente

### 1. As duas Centrais de Protesto falam com o sistema

**O roteiro das Centrais passou de 8 para 13 dos 16 passos.** Antes desta
versão, cinco passos diziam «no site da CENPROT» ou «no site da CRA» e não
tinham tela nenhuma.

| passo | antes | agora |
|---|---|---|
| Recebimento de remessa (CENPROT) | **sem tela** | *Protesto → Pendências da CENPROT* |
| Pedidos de anuência | **sem tela** | baixa, decide, e traz os PDFs assinados |
| Pedido de cancelamento | **sem tela** | informa a Central — **não lavra** |
| Pedido de certidão eletrônica | o pedido chegava no site | chega pela API |
| Arquivo de emolumentos | baixava à mão | **sobe pela API**, o mesmo arquivo |
| Cancelamentos e autorizações (CRA) | **sem tela** | *Protesto → CRA — falar pela API* |

**Onde ficaram no menu:** o Protesto ganhou uma terceira seção. **«O dia da
CRA»** guarda a corrente do dia na ordem do seu roteiro; **«O dia da
CENPROT»** guarda as duas telas dela. A linha direta com a CRA fica no fim da
seção dela, e é só para você e o gerente.

### 2. A senha das Centrais não entra no banco

Você a digita em **Administrativo → Configurações → Centrais de Protesto**, e
ela vai para `%PROGRAMDATA%\CartorioGestao\`, ao lado da do selador. **O banco
viaja no backup, e o backup já saiu da serventia.**

São quatro linhas: CRA e CENPROT, cada uma com homologação e produção.
**Comece pela homologação** — o sistema começa nela por padrão, e a tela avisa
em vermelho quando o ambiente é o de produção.

### 3. O que o sistema recusa fazer, e diz na tela

- **Não lavra ato nenhum pela Central.** O cancelamento continua se lavrando na
  ficha do título, com hipótese do catálogo e fundamento escrito. A tela
  apenas **informa** a Central do que já foi lavrado.
- **A decisão judicial só se baixa.** Ela aparece na fila para o balcão saber
  que existe — e para o título não ser oferecido no «A protestar» sem que
  ninguém veja a ordem. Quem registra a sustação é você, na ficha.
- **A tela da CRA traz o arquivo cru e não aponta nada.** Duas coisas do
  contrato da CRA não estão medidas, e alimentar o leitor com um palpite
  apontaria títulos que ninguém apresentou.

### 4. O balcão do WhatsApp

Uma fila de conversas **dentro** do Cartório Gestão — mesmo login, mesmo
banco. Ela foi construída noutra passada, na mesma árvore, e **viaja neste
pacote**. Quem a construiu documenta o que ela faz.

O que vale saber para aplicar: **ela não liga sozinha.** Sem as credenciais da
Meta informadas, nada acontece.

---

## O QUE ESPERA VOCÊ

1. **A credencial da CENPROT**, na tela de configurações. Você já criou o
   usuário na API deles.
2. **Pedir ao Pessoa Exemplo (P21) o usuário e a senha de homologação da CRA** — e,
   **junto**, alguns títulos de exemplo. Os dois no mesmo pedido: a credencial
   sozinha mede o que a API devolve; **só um título mede o que vai na
   Confirmação e no Retorno**, que são os dois passos com hora marcada (11h30
   e 14h10). Sem título na homologação não há o que confirmar nem o que
   retornar.
3. **Uma coisa a conferir na homologação:** o cancelamento manda um número que
   o contrato chama de `cd_pedido`, e a resposta da Central **não tem campo
   com esse nome** — tem `nr_pedido`. Os exemplos do próprio contrato
   desempatam, mas isso é leitura, e não teste. **A tela mostra o número antes
   de mandar e diz de onde ele saiu.**

---

## AS SETE COISAS PARA CONFERIR DEPOIS DE APLICAR

Se qualquer uma falhar, a atualização não subiu como devia.

| | o que olhar | o que tem de aparecer |
|---|---|---|
| 1 | O menu do Protesto | **três seções**: «O balcão», «O dia da CRA» e **«O dia da CENPROT»** |
| 2 | *Protesto → Pendências da CENPROT* | abre, com as **cinco espécies** no quadro e a faixa amarela de homologação |
| 3 | *Protesto → CRA — falar pela API* | abre, e diz que **força o https** porque o arquivo da Central declara `http://` |
| 4 | *Administrativo → Configurações* | a caixa **Centrais de Protesto**, com **quatro linhas** |
| 5 | *Protesto → O roteiro das Centrais* | a cobertura diz **13 de 16**, e não 8 |
| 6 | Clicar em «Baixar da CENPROT» sem credencial | volta uma **frase em português**, e não um erro do sistema |
| 7 | *Administrativo → O que ficou pelo caminho* | a fonte **«Pendência da CENPROT decidida e não enviada»** aparece na lista de fontes |

---

## O QUE ESTA VERSÃO CORRIGIU DE DENTRO

Coisas que o balcão não vê, e que mudam o que o sistema sabe sobre si mesmo.

**O varredor de acoplamento ao SQLite media a PALAVRA, e não SQL.** Ele
contava `strftime(` no arquivo inteiro — e `datetime.strftime` é Python puro,
que roda igual em qualquer banco. **Dos 35 usos que a lista declarava como
dívida, 4 eram reais.** Onze módulos carregavam dívida inventada, e quem
lesse a lista para saber o tamanho do problema contaria onze a mais.

A régua mudou, e não o número: ele passou a ler o código e a procurar **dentro
das strings**, que é onde SQL mora. **Nada foi consertado para o teto baixar —
o que baixou foi a mentira.**

**Três coisas que faltavam amadurecer**, todas do mesmo tipo — a peça pronta
que ninguém chamava:

- o **valor da retirada** era digitado à mão na tela da CENPROT, e o sistema já
  o calcula (166 de 173 no centavo). Agora vem preenchido, **como sugestão**,
  dizendo de onde veio;
- o roteiro **não contava** os três passos que ganharam tela;
- a **decisão gravada e não enviada** não aparecia em «o que ficou pelo
  caminho», e é literalmente isso.

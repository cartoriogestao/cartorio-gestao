# Roteiro da 3.6.48 — as cores, o usucapião e o acervo que virava pendência

*31/08/2026, feito durante a madrugada*

---

## Primeiro: **um arquivo só, e ele é o único que você precisa aplicar**

| | |
|---|---|
| arquivo | `CartorioGestao_3.6.48.cgu` |
| onde | `C:\Users\<usuario>\Downloads\CartorioGestao\` |
| tamanho | 2.458.929 bytes |
| SHA-256 | ver `CartorioGestao_3.6.48.cgu.sha256`, ao lado do pacote |
| arquivos dentro | 485 (nenhum do runtime) |
| suíte | **3.611 testes, 0 falhas** |

Ele traz tudo o que a 3.6.47 trazia. Se você ainda não aplicou aquela, **aplique
só esta**: o pacote é completo, não incremental.

**O banco migra sozinho.** As colunas novas são seis em `us_movimentos` — o
endereço, a forma, a tentativa e o resultado da notificação do usucapião.
Nenhuma coluna é removida.

---

## #32 — a cor de cada módulo

> «cada módulo deve ter uma cor no layout, cada submódulo deve ter uma derivação
> diferente dessa cor, e precisa reorganizar, unir o que é semelhante»

**A cor é identidade, e não enfeite.** Ela existe para você saber em que
atribuição está antes de ler o título — e perceber quando entrou na errada.
Aparece em três lugares e **nunca no fundo da página**: fundo colorido cansa a
vista de quem passa o dia nele.

E vem **sempre com o nome** por extenso ao lado do título: a cor diz «mudou de
módulo», não diz para qual.

**A primeira paleta eu escolhi a olho, e a medição a desmentiu.** «Livros e
acervo» saiu com **exatamente** o matiz de «atenção», o Registro de Imóveis
colado no de «feito», e o Tabelionato com contraste abaixo do mínimo da norma —
**cor de módulo que parece alarme faz ler alarme onde não há**. Agora se escreve
o matiz e a cor sai de uma conta que garante o contraste.

**Cada seção tem a sua derivação**, mais clara a cada uma. A primeira versão
repetia a partir da quinta — e o maior grupo tem sete.

### Unir o que é semelhante

Medido: **112 links de menu, 111 destinos.** Havia **uma** duplicata —
«Modelos de documento» no RI e «Modelos dos documentos» no Administrativo, que é
o seu relato #12 noutro lugar. Apagar um seria a saída preguiçosa; **o catálogo
já sabia de qual atribuição é cada modelo** e nenhuma tela usava. Agora filtra, e
o link do RI leva aos **5 modelos do RI** em vez dos 12 da casa.

### Colocar em ordem

«O dia» do Registro de Imóveis misturava **três naturezas**: o trabalho do dia,
processos de meses (usucapião, retificação) e uma consulta normativa. Quem o
abria procurando o que fazer agora lia oito linhas e achava quatro. Os processos
ganharam seção própria.

---

## #30 e #21 — o usucapião

> «precisa ter campo para subir as informações necessárias aos atos que o
> cartório precisará praticar, como as notificações, e gerar modelo e manual»

**O rito tem três atos que produzem papel, e nenhum dos três tinha modelo** —
eram etapas com nome e sem papel:

| ato | agora |
|---|---|
| **notificação** | papel com o recibo junto, endereço, forma e prazo da norma |
| **edital** | com a falta de origem consignada, quando é o caso |
| **ofício aos entes** | os **três** de uma vez — União, Estado e Município |

**A regra não foi inventada: foi importada.** O art. 754 manda aplicar o
procedimento da retificação, que este sistema já tinha lido — as formas e os
endereços são os **mesmos objetos**, não uma cópia.

**A procedência de cada prazo fica à vista**: «lido» é o que conferi no PDF do
Código de Normas que está aqui; «citado» vem da Lei de Registros Públicos, cujo
texto **não foi lido dentro da casa**. Onde é «citado», o sistema mostra e **não
impõe** — confirme com a lei aberta. Prazo errado numa notificação não aparece
como erro: aparece como impugnação perdida meses depois.

**A tela mostra o que já se tentou** e qual é a próxima forma da norma, por
destinatário — sem isso, quem expede a segunda notificação repete a mesma forma
ou pula para o edital, que custa, demora, e sem a frustração registrada é nulo.

**As referências à IA saíram.** O que sai é um relatório do processo, o que volta
é um parecer, e quem lê não importa ao módulo. **A proteção continua inteira**: o
parecer entra por conferir, e a decisão recusa fechar o processo apoiado em
parecer que ninguém leu.

---

## #13 — o acervo que virava pendência

> «pendências antigas e do e-ofício não devem aparecer (…) atos novos devem ter
> uma opção facilitada de corrigir»

| tabela | apareciam como «sem selo» | eram do E-Ofício |
|---|---|---|
| `nt_atos` | 260 | 258 |
| `rc_atos` | 244 | 244 |
| `pt_atos` | 2.281 | 2.281 |

**2.783 pendências, e só duas eram desta casa.** Depois do conserto: **10**. O
selo daqueles atos existiu — foi colado como imagem, ou ficou no acervo sem
amarração —, e comprar selo hoje para um ato de 1990 não é conserto: é inventar.

**E o que sai fica contado**, para ninguém concluir que o trabalho acabou.

A outra metade: as telas de carga mostravam o assento retido **e o motivo**, e
paravam ali. **Motivo sem caminho é diagnóstico sem tratamento** — agora há
*abrir e corrigir* em cada linha.

---

## Os passos

1. Feche o sistema no servidor
2. Rode `ATUALIZAR_SISTEMA.cmd`
3. Suba — **o banco migra sozinho**
4. Confira pela tabela abaixo
5. **Suba o `NOTAS_DESENVOLVIMENTO_30-08-2026.txt`** em *Ajuda → Problemas*:
   agora ele traz **25 dos 26 relatos como atendidos**, cada um com a prova de
   onde conferir. Fechar continua sendo o seu clique.

---

## Como conferir que subiu certo

| onde | o que tem de aparecer |
|---|---|
| rodapé | **3.6.48** |
| qualquer tela do RCPN | faixa **azul** no alto e a etiqueta «Registro Civil das Pessoas Naturais» |
| qualquer tela das Notas | faixa **verde-oliva**, e a etiqueta muda junto |
| menu → Registro de Imóveis | a seção **Processos que levam meses** existe |
| menu → RI → Modelos de documento do RI | abre com **5** modelos, e diz que está filtrado |
| ficha de um usucapião | **Expedir notificação** e **Edital e ciência aos entes públicos** |
| **Painel geral** | o atendimento do balcão com **6** — não com 21 mil |

> **A conferência mais rápida é a cor**: se o alto da tela não mudar de cor ao
> passar do Registro Civil para as Notas, a atualização não subiu.

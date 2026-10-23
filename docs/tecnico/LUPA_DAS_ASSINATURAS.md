# A lupa das assinaturas — v3.3.2

**17/08/2026.** Está construído e testado fora do ar. Nada disso vale no sistema enquanto o
`ATUALIZAR_SISTEMA.cmd` não rodar.

---

## O que muda

Toda assinatura digitalizada passou a abrir com um clique, sobreposta à tela, ampliável.

Onde vale:

- **Cartão de autógrafo** — as vias da pessoa, lado a lado
- **Reconhecer firma** — o balcão, com a pessoa na frente
- **Reconhecimento já gravado** — o que se reabre quando alguém questiona depois
- **Cartões de autógrafo** (lista da busca) e **atos de livro**
- **Fichas do Registro de Imóveis** — a mesma lupa, na matrícula e na conferência lado a lado

Dentro da lupa:

| Gesto | O que faz |
|---|---|
| roda do mouse | amplia mirando o ponteiro |
| arrastar | move a imagem |
| duplo clique | alterna entre "cabe na tela" e tamanho real |
| `+` `−` `0` | aproxima, afasta, ajusta |
| `G` | gira 90 graus |
| `C` | inverte claro e escuro |
| `D` | põe duas vias lado a lado, com o mesmo zoom nas duas |
| `←` `→` | passa de uma via a outra |
| `Esc` | fecha |

**Baixar** salva o arquivo como ele está no disco — serve para anexar a assinatura numa resposta
a ofício, ou para abrir num programa de imagem quando a dúvida é sobre o próprio traço.

---

## Por que isso não era um detalhe

A assinatura aparecia numa miniatura de 200 pixels, parada, sem clique.

Reconhecimento por semelhança é o tabelião confrontando o traço com o cartão de autógrafo. O que
se confere é a inclinação, o ponto onde a caneta levanta, o laço do sobrenome — nada disso cabe
em 200 pixels. E é o único ato deste sistema que não tem conserto depois, porque a firma já saiu
reconhecida.

---

## Três defeitos calados que apareceram no caminho

**1. A atualização não levaria a lupa.**
O `ATUALIZAR_SISTEMA.cmd` copiava `*.css` da pasta `static` — e mais nada. Enquanto a pasta tinha
um arquivo de estilo e nada além, a lista funcionou. O `lupa.js` ficaria para trás, o sistema
subiria inteiro, sem erro nenhum, e as assinaturas continuariam não abrindo ao clique. Agora
copia a pasta toda e **confere que o arquivo chegou**, avisando se não chegou.

**2. Dois arquivos saíam com o tipo errado.**
A rota da imagem rotulava `.jpg` como `image/jpeg` e **todo o resto** como `image/png`. Das 3.637
assinaturas do acervo, 3.635 são JPG — as outras duas são uma GIF e um PDF, e as duas saíam
mentindo o formato. O PDF nem imagem é. Dois arquivos em três mil e seiscentos não parece muito
até ser o cartão da pessoa que está no balcão.

Agora: cada formato sai com o seu tipo; TIFF e afins são convertidos para PNG na hora (o mesmo
que já se faz com as fichas do Registro de Imóveis); o PDF vai inteiro para o navegador, que sabe
abri-lo; e arquivo corrompido vira download com aviso, em vez de derrubar a tela das outras vinte
assinaturas da mesma página.

**3. Girar cortava a imagem.**
Ficha deitada girada para a vertical passa a caber de outro jeito. Pelo botão, a conta do "cabe
na tela" não era refeita e a imagem aparecia cortada; pela tecla `G`, era. Dois caminhos para a
mesma ação, um deles errado. Agora é um só.

---

## O que ainda falta, e é o motivo de hoje não abrir nada

O `DIAGNOSTICAR_FIRMAS.cmd` de hoje, 10h46, responde:

```
cartoes de autografo         0
linhas em nt_cartao_imagens  0
com nome de arquivo          0

>>> NAO HA O QUE LOCALIZAR: a tabela esta sem nome de arquivo.
>>> A importacao das firmas do E-Oficio precisa rodar antes.
```

**As imagens estão no disco.** O `COPIAR_ARQUIVOS_EOFICIO` já trouxe as 3.644 firmas de
`\\servidor\C11\Firmas` para dentro do acervo. O que não rodou foi a carga do banco: sem ela não
há cartão, não há linha em `nt_cartao_imagens`, e não há o que a lupa abra.

Ordem, então:

1. **`ATUALIZAR_SISTEMA.cmd`** — pede Administrador; confirme **Sim**.
2. **Menu → Tabelionato de Notas → Trazer notas do E-Ofício** — traz 4.060 cartões, 3.637
   assinaturas, 13.209 reconhecimentos, 3.539 autenticações, 213 procurações, 45 escrituras e
   301 modelos. Pode rodar quantas vezes precisar.
3. **Menu → Assinaturas digitalizadas** → *Localizar arquivos* — casa cada nome do banco com o
   arquivo no disco.
4. Abra um cartão qualquer e clique na assinatura.

Se depois disso alguma não abrir, o `FERRAMENTAS\DIAGNOSTICAR_FIRMAS.cmd` diz de qual dos lados é
o problema — o banco, o disco, ou o Pillow.

---

## Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `static/lupa.js` | **novo** — a lupa inteira, sem biblioteca de fora |
| `static/app.css` | a aparência da lupa, e a miniatura passa a parecer clicável |
| `templates/base.html` | carrega o `lupa.js` em toda tela |
| `templates/notas_cartao.html` | as vias do cartão, agrupadas para comparar |
| `templates/notas_reconhecimento.html` | o balcão |
| `templates/notas_reconhecimento_ver.html` | o reconhecimento gravado |
| `templates/notas_cartoes.html`, `notas_ato.html` | listas |
| `templates/ri_ficha.html`, `ri_conferir.html` | as fichas do Registro de Imóveis |
| `notas_web.py` | formatos, tamanho pedido, e a rota de baixar o original |
| `SERVIDOR/ATUALIZAR_SISTEMA.cmd` | copia a pasta `static` inteira e confere que chegou |
| `tests/test_lupa_assinaturas.py` | **novo** — 11 testes das rotas e das telas |
| `app.py`, `VERSAO.txt` | 3.3.1 → 3.3.2 |

**Sem biblioteca de fora, de propósito.** O sistema roda na rede da serventia e há máquina que não
alcança a internet. Biblioteca de CDN seria uma lupa que funciona no escritório e falha no
balcão — que é justamente onde ela precisa funcionar.

---

## Conferência

- 202 testes passando (191 que já existiam, mais 11 novos)
- Sistema subido com um cartão de três vias — JPG, JPEG e TIFF — e as rotas conferidas uma a uma:
  JPG intacto, TIFF convertido, miniatura no tamanho pedido, original baixando com o nome certo,
  imagem inexistente respondendo 404 e não 500, arquivo corrompido virando download em vez de
  derrubar a tela
- 32 verificações do comportamento da lupa: abrir, zoom, limites, girar, contraste, trocar de
  via, comparar duas com zoom sincronizado, recado de arquivo que não abre, e fechar

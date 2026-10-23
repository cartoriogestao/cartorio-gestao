# A etiqueta do reconhecimento de firma — v3.3.5

**17/08/2026.** Construído e testado fora do ar. Nada vale enquanto o `ATUALIZAR_SISTEMA.cmd`
não rodar.

---

## O que passa a existir

Botão **Imprimir etiqueta** na tela do reconhecimento e um atalho na lista, para reimprimir sem
abrir o ato. A janela de impressão abre sozinha; escolha a impressora térmica e mande.

Tamanho: **100 × 30 mm**, como você informou. Ajustável em **Tabelionato de Notas → Ajustar
etiqueta**.

---

## O teor saiu do acervo, não de uma suposição

O E-Ofício guardou o texto exato de cada uma das 13.209 etiquetas. Este é o de 19/03/2020:

```
RECONHECO POR SEMELHANCA A FIRMA DE ESCREVENTE. DOU FE.
EM TEST.________ DA VERDADE. CIDADE EXEMPLO-MA,19/03/2020.
```

O sistema novo montava só até o **"DOU FÉ."** — o que basta na tela e não basta na tira, porque
o fecho é o lugar do sinal público e da data do ato. Agora monta o teor completo, no mesmo
formato.

**Não duplica.** Os reconhecimentos importados já trazem o texto inteiro; reimprimir a segunda
via de um ato de 2020 sai igual à primeira, e não com "DA VERDADE" duas vezes.

Na tira saem ainda: **selo**, **código de segurança**, e **quem reconheceu com a função** — que
só agora sai certa (ver `ATUALIZACAO_3.3.3.md`).

---

## O QR do selo

O selo tem 28 caracteres — `RECFIR000000D0XB4FK298AWP401`. Quem recebe o documento e quer
conferir precisa digitar os 28 sem errar um. Na prática, ninguém confere. Com o QR, aponta a
câmera.

**O QR leva a https://selo.tjma.jus.br/** — o Portal do Selo Eletrônico do TJMA. Confirmei em
duas fontes independentes: a página do próprio tribunal (*Selo de Fiscalização* → “Para conferir
a autenticidade do SELO DE FISCALIZAÇÃO ELETRÔNICO, click no banner abaixo”) e o rodapé das
certidões que esta serventia já emitiu, que traz impresso “Consulte em
https://selo.tjma.jus.br”.

### O que eu não consegui confirmar — e como resolvi

**Se o portal aceita o selo pela URL**, de modo a abrir a consulta já preenchida. O portal é uma
aplicação de tela e o tribunal não publica o formato do link direto.

Por isso **o conteúdo do QR é um campo na tela Ajustar etiqueta**, e não algo fixo no código. O
padrão é `https://selo.tjma.jus.br/?selo={selo}`:

- se o parâmetro for aceito, abre preenchido;
- se for ignorado, abre a tela de consulta e o número está impresso ao lado do QR para digitar.

Nenhum dos dois quebra. No dia em que a corregedoria publicar o link oficial, é esse campo — não
uma atualização do sistema. `{selo}` e `{codigo}` são trocados pelos valores do ato; em branco, o
QR carrega só o número do selo, que qualquer leitor mostra na tela mesmo sem internet.

**Confira o QR com o celular antes de usar no balcão.** A tela de ajuste mostra exatamente qual
endereço ele carrega.

### Decisões técnicas

**O número continua impresso ao lado do QR.** QR borrado na térmica, etiqueta amassada no bolso,
câmera de celular velho — o número legível é o que sobra quando o QR falha. Num documento que
vale por décadas, redundância não é desperdício.

**16 mm, e o QR foi lido de volta antes de eu confiar nele.** Desenhei o QR no tamanho físico e
decodifiquei a 203 e a 300 pontos por polegada — as duas resoluções de térmica que existem no
balcão. Leu em 14, 16 e 18 mm; abaixo de 14 começa a falhar. 16 fica no meio, com folga dos dois
lados. Gerar um QR bonito que nenhuma câmera lê seria pior do que não ter QR.

**SVG, não imagem.** Imagem pronta tem uma resolução só e sai serrilhada numa das duas
densidades; o SVG é desenho vetorial e sai exato nas duas. E cabe dentro do próprio HTML, sem
arquivo no disco.

**Sem selo, não há QR.** Um QR que aponta para uma consulta vazia é pior que nenhum: parece
conferível e não é.

**Sem a biblioteca, a etiqueta sai igual.** Faltando o `segno` no servidor, a tira sai com o
número do selo e a tela diz o que instalar. Biblioteca ausente não impede o balcão de imprimir.

---

## Por que HTML e não comando de impressora

Impressora térmica de etiqueta se instala no Windows como impressora comum. Mandar bytes crus
(ESC/POS, ZPL) para a porta exigiria um programa rodando em cada máquina do balcão — mais um
para instalar, manter e consertar.

Uma página com `@page { size: 100mm 30mm; margin: 0 }` sai pela mesma impressora, pelo mesmo
driver, sem instalar nada. E funciona igual na Elgin, na Bematech e na Argox, o que não se pode
dizer de nenhum comando ESC/POS.

**Na janela de impressão, escala em 100%.** "Ajustar à página" encolhe a etiqueta e desalinha
tudo — é o defeito mais comum desse tipo de impressão.

---

## Três coisas que a etiqueta se recusa a fazer

**Não imprime ato cancelado.** Etiqueta de ato cancelado colada num documento é o ato valendo no
mundo depois de ter sido desfeito no livro.

**Não sai calada sem selo.** A tira sai, mas a tela avisa em cima que o selo não foi anotado —
etiqueta sem selo colada num documento é um reconhecimento que ninguém consegue conferir depois.

**Não corta o teor em silêncio.** A tira tem que ter recorte, senão o texto vaza na etiqueta
seguinte do rolo. Mas cortar o teor de um ato notarial sem avisar seria o pior defeito possível:
a etiqueta sai bonita, é colada, e o "DOU FÉ" ficou de fora. Se o conteúdo não couber, a tela
avisa em vermelho, diz quantos milímetros faltam, e **não abre a impressão sozinha**.

---

## O corpo da letra foi medido, não escolhido no olho

O QR come 16 mm da largura. Desenhei a etiqueta em tamanho físico e contei as linhas em Arial
Narrow, na coluna de 78 mm que sobra:

| corpo | 1 firma | 3 firmas | 5 firmas (extremo) |
|---|---|---|---|
| 7,5 pt | 2 linhas, sobra 14,7 mm | 4 linhas, sobra 8,7 mm | 5 linhas, sobra 5,7 mm |
| **8 pt** | 3 linhas, sobra 10,7 mm | 4 linhas, sobra 7,5 mm | 5 linhas, sobra 4,3 mm |
| 8,5 pt | 3 linhas, sobra 9,9 mm | 4 linhas, sobra 6,5 mm | **não cabe** |

**8 pt** é o maior corpo que sobrevive ao pior caso realista — cinco firmas de nomes longos na
mesma tira, com o QR ao lado. Letra de etiqueta de firma é para ser lida por quem recebe o
documento; deixar menor quando cabe maior é economizar espaço que ninguém pediu.

---

## Ajustar na impressora, sem gastar o rolo

**Tabelionato de Notas → Ajustar etiqueta.** Largura, altura, margem, corpo da letra, entrelinha
e deslocamento horizontal/vertical.

O deslocamento existe porque driver de térmica empurra a impressão meio milímetro para um lado, e
não há como corrigir isso na impressora. Aceita vírgula (`0,5`), porque o teclado é brasileiro.

**Como acertar:** imprima a página de teste numa folha comum, ponha uma etiqueta do rolo em cima
contra a luz, veja o quanto está fora, corrija, repita. Só depois de encaixar é que vale gastar
tira. A página de teste sai com régua de 100 mm marcada de 10 em 10 — se ela não medir 10 cm na
régua de verdade, a escala não está em 100%.

Medida inválida não apaga a etiqueta: alguém digita "10 mm" com a unidade junto e o sistema volta
ao padrão em vez de imprimir em branco.

---

## Reimpressão

Etiqueta térmica enrosca, sai torta e sai em branco quando o rolo acaba. Reimprimir é rotina, não
exceção.

O sistema conta quantas vezes cada etiqueta saiu e mostra na tela do ato e na lista. Não é
estatística: é para o balcão não colar duas no mesmo documento nem deixar um sem nenhuma. Toda
impressão fica na auditoria.

---

## Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `notas_selo.py` | **novo** — o QR do selo, e por que o conteúdo é configurável |
| `templates/notas_etiqueta.html` | **nova** — a tira, no tamanho exato, com o QR |
| `templates/notas_etiqueta_ajuste.html` | **nova** — medidas, conteúdo do QR e teste com régua |
| `notas_schema.py` | `texto_da_etiqueta` com o fecho do E-Ofício; colunas da contagem |
| `notas_web.py` | rotas de impressão e de ajuste; medida ausente não derruba a gravação |
| `templates/notas_reconhecimento_ver.html` | botão, aviso de selo, contagem |
| `templates/notas_reconhecimentos.html` | atalho de reimpressão na lista |
| `templates/base.html` | menu **Ajustar etiqueta** |
| `requirements.txt`, `SERVIDOR\ATUALIZAR_SISTEMA.cmd` | `segno` |
| `tests/test_etiqueta_reconhecimento.py` | **novo** — 27 testes |
| `app.py`, `VERSAO.txt` | 3.3.3 → 3.3.5 |

---

## Um defeito que apareceu no caminho

Ao acrescentar o tamanho do QR às medidas, os formulários **já abertos** no navegador do balcão
deixaram de salvar qualquer coisa: o campo novo não existia neles, virava string vazia, e a tela
recusava a gravação inteira dizendo que `''` não é número — sem dizer de qual campo.

Não era hipótese, aconteceu nos testes. Corrigido: campo ausente significa “não mexi nisso” e
fica como está; só campo presente e inválido é erro, e aí a mensagem diz qual é. Toda medida
acrescentada daqui em diante teria repetido isso.

---

## Conferência

- **257 testes passando** (191 que já existiam, mais 66 destas rodadas)
- **O QR foi lido de volta**, não só gerado: desenhado no tamanho físico e decodificado a 203 e a
  300 DPI, nos tamanhos 14, 16 e 18 mm. Todos leram o endereço certo
- Etiqueta desenhada em tamanho físico a 300 DPI e conferida no papel: com o QR ao lado, cabe com
  7,5 mm de folga no caso de três firmas
- Testado: teor completo, fecho não duplicado em ato importado, tamanho de papel no CSS, ausência
  do menu do sistema na página impressa, selo e código na tira, QR presente com selo e ausente
  sem selo, número impresso ao lado do QR, conteúdo do QR configurável, servidor sem a biblioteca
  imprimindo do mesmo jeito, ato cancelado recusado sem contar impressão, reimpressão contada,
  auditoria registrada, medida com vírgula aceita, medida absurda caindo no padrão e campo
  ausente não derrubando a gravação

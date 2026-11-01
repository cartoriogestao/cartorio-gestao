# Revisão dos livros do RCPJ e do RTD (01/11/2026)

Pedido: abas do Livro de Protocolo e dos demais livros obrigatórios, nos termos da Lei
6.015/1973, do Código Nacional de Normas (Provimento 149/CNJ) e do Código de Normas da
CGJ/TJMA (CN-MA). Norma estadual: quem usa o sistema noutro estado confere a do seu.

## O que passou a existir

| Livro | Fonte | Onde |
|---|---|---|
| RCPJ: Livro de Protocolo | CN-MA art. 403 | Livros → RCPJ → Protocolo |
| RCPJ: Livros A e B | Lei 6.015, art. 116; CN-MA art. 402 | Livros → RCPJ |
| RCPJ: Índices cronológico e alfabético | CN-MA art. 404 | Livros → RCPJ → Índices |
| RTD: Livro A, Protocolo | Lei 6.015, art. 132, I; CN-MA arts. 963, I, e 966 | Livros → RTD → Livro A |
| RTD: Livros B e C | Lei 6.015, art. 132, II e III; CN-MA art. 963 | Livros → RTD |
| RTD: Livro D, Indicador Pessoal | Lei 6.015, art. 132, IV; CN-MA art. 963, IV e § 5º | Livros → RTD → Livro D |
| RTD: Livro E, Indicador Real | Lei 6.015, art. 132, V | Livros → RTD → Livro E |
| RTD: Livro F, facultativo | Lei 6.015, art. 132, VI; CN-MA art. 957, §§ 4º e 5º | Livros → RTD → Livro F |
| RTD: Livro G, apresentantes do F | Lei 6.015, art. 132, VII | Livros → RTD → Livro G |

Também: a espécie de lançamento (art. 966, III), a referência ao lançamento no Protocolo
(art. 968), os pendentes com o motivo no termo do dia (art. 970), o recibo com a previsão
de entrega (art. 974, § 1º), a anotação para o título (art. 966, § 2º), a data da
assinatura (art. 958, § 4º) e a lista do que conferir, com o artigo (`rg_normas`).

O Código Nacional de Normas trata aqui do PLD (arts. 163-164, já em `pld`), dos livros
administrativos (arts. 185-191, já em `livros_administrativos`) e da alienação fiduciária
(arts. 397-A a 397-AM, Provimento CN 196/2025, em `rg_fiduciaria`).

## Construído depois dos livros

- **Alienação fiduciária (CN arts. 397-A a 397-AM; CN-MA arts. 955 e 956):** autuação com
  numeração própria, conferência do requerimento, prazos, linha do tempo, peças. É o controle
  da serventia: o art. 397-G dá a gestão nacional ao módulo da Central, e não há contrato
  medido dele. O sistema não lança no Renavam nem na Central: marca o que foi feito lá.
- **Sobrestamento (CN-MA arts. 971 e 975):** `rg_sobrestamentos`. O título mantém número, data
  e situação, e qualificar, registrar e concluir recusam enquanto durar.
- **DOI do RTD (CN-MA art. 962):** `rg_doi`, na mesma tela e no mesmo arquivo da serventia,
  com tipo de serviço 3 e natureza 1 do layout do DOI-Web.
- **Nome parecido (CN-MA art. 402, § 1º):** compara o núcleo do nome e só levanta a mão.
- **Livro Auxiliar do B (CN-MA art. 964):** aba com as cópias anexadas a cada ato do Livro B.

## O que continua fora, e por quê

- **Envio à Central e ao Renavam:** sem contrato medido da API desse módulo.
- **Emolumentos do processo (CN art. 397-N):** a cobrança e o selo seguem pelo registro ou pela
  averbação da carta. Item próprio na tabela do estado não foi achado.
- **Outra serventia da comarca (CN-MA art. 402, § 2º):** fica na lista do que conferir, porque o
  sistema não enxerga as outras. Em ofício único não se aplica.

## Leituras de prazo a confirmar

- **Início dos 20 dias corridos:** o primeiro dia útil depois da ciência conta como dia 1.
- **Sem impugnação, entrega do bem:** o art. 397-V, III, b, diz «no mesmo prazo», e o art. 397-AF
  fala em 20 dias depois do não pagamento. O sistema usa o mesmo prazo quando não há impugnação
  e 20 novos depois de indeferida ou não conhecida.
- **Reversão depois de entrega voluntária:** o art. 397-AK fala de bem apreendido, e o 397-AL
  cobre os dois casos. O sistema dá 5 dias úteis nos dois.

## Regras de leitura

- Os livros são montados do que foi lançado; o que o ato não guardou fica em branco.
- O acervo não diz a letra do livro do RTD: tudo veio em `TD_B`, com o volume ao lado. Por
  isso os Livros C, F e G só têm o que for lançado daqui em diante.
- `rg_partes` e `rg_bens` são cadastro em volta do registro: não mudam teor nem tomam
  número. O que sai deles sai com motivo escrito, e a linha fica.
- O Livro F fica fora do Livro D, porque não dá publicidade (CN-MA art. 957, § 5º).
- A carga `rcpj_rtd_livros` é repetível, não chama o núcleo e não mexe em contador.

## O número do protocolo

O contador do E-Ofício voltou para trás: o RTD foi até 1512 e recomeçou em 1270 em
04/12/2024; o RCPJ foi até 1501 e aparece em 1273 em 31/12/2025. A carga declara a pendência
em «O que falta informar», e a escolha do próximo número é do oficial.

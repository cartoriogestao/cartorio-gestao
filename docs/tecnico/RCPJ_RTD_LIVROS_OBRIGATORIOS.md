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

O Código Nacional de Normas trata aqui do PLD (arts. 163-164, já em `pld`) e dos livros
administrativos (arts. 185-191, já em `livros_administrativos`). Nada novo saiu dele.

## O que ficou de fora, de propósito

- **Busca e apreensão e consolidação fiduciária (CN-MA arts. 955 e 956):** é procedimento
  próprio, e o sistema não o conduz. A ficha avisa quando a natureza cita o caso.
- **DOI do instrumento particular no RTD (CN-MA art. 962):** a ficha lembra; a declaração
  não sai deste caminho.
- **Sobrestamento por suspeita de falsificação (CN-MA art. 975, §§ 1º a 3º):** não há
  situação própria no título. Hoje fica na observação e na qualificação.
- **«Semelhante» do art. 402, § 1º, e outra serventia da comarca (§ 2º):** a conferência
  acha só o nome igual, nesta serventia.
- **Livro Auxiliar do B (CN-MA art. 964):** facultativo, e só sem escrituração eletrônica.

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

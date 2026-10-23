# O agente de minutas do RI e das Notas

Construído no SANDBOX em 23/10/2026. Ainda **não está na produção**: entra com o
próximo pacote, quando o oficial pedir.

## O pedido

> «agora vamos criar um agente para preparar as minutas dos atos do RI e do Notas
> (escrituras, procurações e atas notariais), nos moldes que temos no RCPN, mas com
> algumas alterações. O agente usaria a API do claude em opus high para ler a
> documentação do sistema presente no protocolo geral e na prenotação ligadas à
> matrícula (usuário poderia selecionar antes de ligar o agente) ou própria
> documentação anexada no momento de pedido ao agente (que já seria anexada no
> arquivamento do ato). Esse agente teria que gerar a minuta, mas precisaria ter
> espaço para instruções iniciais e instruções de revisão (caso escrevente precise
> pedir para mudar alguma coisa).» — o oficial, 23/10/2026

## Onde ele aparece

Ele fica num quadro chamado **«Agente de minutas (IA)»**, em duas telas:

| Atribuição | Tela | Onde a minuta pousa |
|---|---|---|
| Registro de Imóveis | ficha da matrícula, logo acima de «Minutas a revisar e lavrar» | `ri_minutas`, na situação **A_REVISAR**. É a mesma fila das minutas importadas, e quem lavra continua sendo a tela de sempre |
| Notas | tela do ato **em lavratura**, logo depois dos documentos para qualificação | o **teor do ato**, o mesmo campo que «Montar» e «Preencher a partir do modelo» gravam |

Nas Notas ele atende escritura, procuração, procuração previdenciária,
substabelecimento, revogação, ata notarial e ata para usucapião. Testamento fica de
fora, porque ele se lavra pelo que o testador declara, e não a partir de documento.

## Como se usa

1. **Escolher os documentos.** O quadro lista o que o sistema já guarda.
   - **RI:** os anexos de cada prenotação da matrícula e os do protocolo geral
     ligado a ela.
   - **Notas:** os anexos do ato e os do protocolo geral ligado a ele.

   Todos vêm marcados, e quem pede desmarca o que não fundamenta o ato.
2. **Juntar documentos agora, se for o caso** (PDF, JPG ou PNG, até 25 MB cada).
   Eles ficam guardados onde o ato os arquiva:
   - **RI:** na prenotação escolhida, de onde a tela de lavrar os mostra;
   - **Notas:** nos documentos do próprio ato, que são o arquivamento dele.
3. **Instruções iniciais** (opcionais), por exemplo «compra e venda da parte ideal
   de 50%».
4. **«Preparar a minuta com o agente».** O pedido roda em segundo plano, e o quadro
   se atualiza sozinho quando ele termina. Leva alguns minutos.
5. **Revisar.** Na versão pronta há o campo **«Instruções de revisão»**. A revisão
   parte do texto **como ele está agora**, inclusive com o que a pessoa já corrigiu à
   mão, e pousa na mesma minuta. Também é possível juntar mais documentos na
   revisão.
6. **«Ver a versão inteira».** A página da versão mostra:
   - o texto;
   - as partes que o agente achou;
   - o que ele não conseguiu afirmar;
   - de que documento e página saiu cada dado importante.

## O que ele faz e o que não faz

- **Ele redige.** Lê os documentos marcados, a ficha da matrícula (ou o ato com as
  partes cadastradas e o modelo escolhido) e dois atos desta casa da mesma espécie,
  que servem de exemplo de redação («na dúvida, faça como a casa faz»).
- **Ele não inventa.** O que falta ou está ilegível sai no texto como
  **[COMPLETAR: …]** e na lista de pendências. Nas Notas, esse marcador já é campo
  em branco para a trava da lavratura.
- **Ele não lavra, não numera, não sela, não cobra e não lança no livro.** Há teste
  que varre os nomes do módulo. O enquadramento é o do Código de Normas do MA,
  arts. 169, I, 171 e 176: a IA redige, e quem pratica o ato é a pessoa.
- **Ele não sobrescreve calado.**
  - Se alguém mexeu na minuta (ou no teor do ato) enquanto ele trabalhava, a
    versão dele fica guardada, e a troca é um clique de quem decide («Usar esta
    versão»).
  - Quando pousa, o texto que estava lá fica guardado no pedido
    (`texto_substituido`).
- **Toda versão fica.** Cada pedido é uma linha de `mi_pedidos`, e a revisão aponta
  para o pedido anterior.

## O modelo e o custo

- **Modelo e esforço:** `claude-opus-5-5`, esforço **high**, como o oficial pediu.
  O pensamento do modelo conta dentro de um teto de 32 mil tokens de saída, e o
  pedido espera até 15 minutos.
- **Documentos:** sobem **inteiros e sem máscara**, como na leitura do RCPN
  (decisão do oficial de 12/10/2026). O PDF vai como documento, a foto como imagem
  reduzida, e Word e ODT viram texto aqui. O limite é de 20 arquivos e 21 MB por
  pedido.
- **Desvio quando o modelo recusa:** está ligado (`fallbacks: "default"`). Se o
  filtro do provedor recusar o pedido, outro modelo responde, e a tela diz qual.
- **Teto:** 60 pedidos por dia (`ia_catalogo.CHAMADAS_POR_DIA["minuta_ia"]`). O uso
  fica no registro de IA, finalidade `minuta_ia`.
- **Custo estimado:** ainda não medido em pedido real. O SANDBOX tem IA simulada, e
  o agente recusa ali dizendo isso. Pela tabela de preços (US$ 4 por milhão de
  tokens de entrada e US$ 20 por milhão de saída), uma escritura de 20 páginas fica
  na casa de US$ 0,30 a US$ 0,80 por pedido. **A CONFERIR** no primeiro uso.

## Os arquivos

| Arquivo | O que é |
|---|---|
| `minuta_ia.py` | o domínio: a tabela `mi_pedidos`, os documentos, o contexto, a instrução, a execução e o pousar |
| `minuta_ia_web.py` | as quatro rotas e o quadro nas duas telas |
| `templates/_agente_de_minuta.html` · `templates/minuta_ia_pedido.html` | o quadro e a página da versão |
| `agente_provedores.py` | o transporte ganhou, só por acréscimo, o documento PDF, o esforço, o formato da resposta e o desvio |
| `ia_catalogo.py` | a entrada `minuta_ia` e o teto |
| `tests/test_minuta_ia.py` | 15 testes, todos sem rede |

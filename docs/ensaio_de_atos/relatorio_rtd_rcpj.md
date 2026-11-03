# Relatório do ensaio de atos — RTD e RCPJ (primeira leva)

Ensaio de 03/11/2026, pedido do oficial de 01/11/2026. O inventário está em `inventario_rtd_rcpj.md`; o
teste em `tests/test_ensaio_de_atos_rtd_rcpj.py`.

**Como foi feito.** `tests/test_fluxo_rtd_rcpj.py` já leva cada ato do protocolo pago ao termo e à certidão,
cada um num registro limpo. Esta leva praticou, pelas mesmas telas e com os mesmos auxiliares de lá
(`Balcao`, `_lavrar_pelo_titulo`), o que vem **depois** e o que se **repete**:
- a averbação sobre o registro cancelado;
- o breve relato da associação dissolvida;
- a segunda associação com a mesma denominação;
- a sociedade empresária apresentada ao RCPJ.

A trava ficou ligada; a única porta aberta foi a do selador de mentira, em 127.0.0.1.

**Resultado.** Estão certos e conferidos:
- **a averbação sobre o registro cancelado é recusada** («só se averba registro ativo»), e nada se lavra;
- **o breve relato da associação dissolvida** é recusado enquanto a leitura da ficha é anterior à
  dissolução; relida a ficha, ele sai e diz «encontra-se CANCELADO», com o cancelamento como último ato.

Ficou **um defeito**, em `xfail(strict=True)`, e quatro observações.

Os nomes e os documentos são fictícios. Os textos do CN-MA não estão nesta máquina: onde ele pesaria,
está escrito «conferir».

---

## 1. A segunda associação com a mesma denominação se inscreve sem aviso

**O que se fez.** A ASSOCIAÇÃO DE EXEMPLO inscrita no Livro A, pelo caminho inteiro. Depois, outro
estatuto, de outra associação com a mesma denominação: recebimento, pagamento, qualificação positiva e
registro.

**O que saiu.** Inscrita sob o nº 2. Nenhuma das três telas (a ficha do título, a qualificação, o
registro) diz que já há uma pessoa jurídica com aquele nome no livro.

**Por que está errado.** CC art. 1.155, parágrafo único: a denominação das associações e fundações
equipara-se ao nome empresarial, para os efeitos da proteção da lei. Art. 1.163: o nome deve distinguir-se
de qualquer outro já inscrito no mesmo registro. O CN-MA tem regra própria da homonímia no RCPJ:
**conferir**.

**Proposta, para o oficial decidir.** Na qualificação do título do Livro A, procurar no RCPJ a mesma
denominação (sem acento, sem caixa, sem a sigla do tipo) em registro ativo e mostrá-la, com o número e
a data. Pergunta: **(m1)** barrar a qualificação positiva enquanto houver nome igual; ou **(m2)** avisar
e pedir a fundamentação, que o escrevente já escreve? A sugestão é a (m2) para nome parecido e a (m1)
para nome idêntico.

---

## Observações (sem teste)

**O1. A sociedade empresária entra no RCPJ sem aviso.** O «Contrato social de sociedade empresária
limitada» foi inscrito no Livro A, como uma associação. A sociedade empresária se registra na Junta
Comercial (CC arts. 967 e 1.150), e o RCPJ é das sociedades simples, associações e fundações (CC art.
1.150; LRP art. 114). O sistema não tem como saber, porque a natureza é texto livre. A tela já pergunta o
enquadramento do CN-MA (arts. 410, 412 e 413). Para o oficial: perguntar também, no Livro A, se é
sociedade simples, associação, fundação ou outra, e avisar quando a natureza diz «empresária»?

**O2. O registro no domicílio das partes (LRP art. 130) não tem como ser conferido.** O título do RTD
guarda o apresentante, mas não as partes do contrato nem o domicílio delas. Pergunta ao oficial: a casa
confere isso no balcão, no papel? Se a resposta for que deveria conferir no sistema, faltam os campos.

**O3. O registro com valor declarado (serviços 305 e 307).** O valor declarado se grava no título
(`rg_titulos.valor_declarado`), mas o item da tabela se escolhe à mão no caixa, e o valor não entra no
selo: o RTD/RCPJ sela por `atos-em-geral` (`ato_selado.caminho_do_rtdpj`). A cobertura já marca «✗ sem
teste». O ensaio não pratica isto sem saber como a tabela do TJMA cobra o RTD com valor (faixa ou
percentual), e o que o selo do TJMA espera. Pergunta ao oficial: a casa registra títulos com valor? Por
qual item?

**O4. A leitura da ficha e o ato do mesmo segundo.** O breve relato só sai se a leitura da ficha é
posterior ao último ato, e a régua compara as horas ao segundo, com «maior que»
(`atrib_certidao`, `criado_em > pj_dados_em`). No mesmo segundo, a leitura conta como atual. O ensaio
caiu nisso: gravou os dados e dissolveu a associação no mesmo segundo, e o breve relato saiu sem a
releitura. No balcão é quase impossível, mas a régua fica mais segura se o empate contar como leitura
velha (`>=`), ou se comparar pela ordem dos atos, e não pela hora. Conserto de um caractere, para o PR de
consertos do RCPJ.

## O que fica para as próximas levas

- a notificação sobre o registro cancelado;
- a averbação de alteração estatutária que muda a denominação, e o breve relato depois dela;
- o RTD: o mesmo título registrado duas vezes (o registro facultativo, Livro F, admite; o B e o C?).

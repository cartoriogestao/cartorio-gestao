# Relatório do ensaio de atos — RTD e RCPJ (primeira e segunda levas)

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

Ficou **um defeito**, em `xfail(strict=True)`, e quatro observações. A segunda leva acrescentou mais um
defeito (item 2) e uma observação (O5).

Os nomes e os documentos são fictícios. Os textos do CN-MA não estão nesta máquina: onde ele pesaria,
está escrito «conferir».

---

## 1. A segunda associação com a mesma denominação se inscreve sem aviso

**CONSERTADO em 03/11/2026** (decisão do oficial, «m»). No registro do Livro A pela tela,
`rg_titulo.denominacoes_em_conflito` compara com as pessoas jurídicas ATIVAS do Livro A. O nome
**idêntico** (as mesmas palavras, sem acento, caixa nem pontuação) é recusado. O **parecido** (as mesmas
palavras depois de tirar o tipo e as de ligação) pede a fundamentação, que vai à auditoria
(`RG_DENOMINACAO_PARECIDA`). A ficha do título avisa antes do clique. A régua fica no registro, e não na
qualificação, porque o título de averbação também chega pelo Livro A, com o mesmo nome.

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

**O1. A sociedade empresária entra no RCPJ sem aviso.** **DECIDIDO E CONSERTADO em 03/11/2026** (o oficial, «n»): o
registro no Livro A pergunta a forma da pessoa jurídica (`rg_titulo.FORMAS_DA_PJ`, gravada em
`rg_registros.pj_forma`), e a tela avisa quando a natureza diz «empresária», na ficha do título e depois
do registro. Avisa, e não barra. O texto original da observação segue abaixo. O «Contrato social de sociedade empresária
limitada» foi inscrito no Livro A, como uma associação. A sociedade empresária se registra na Junta
Comercial (CC arts. 967 e 1.150), e o RCPJ é das sociedades simples, associações e fundações (CC art.
1.150; LRP art. 114). O sistema não tem como saber, porque a natureza é texto livre. A tela já pergunta o
enquadramento do CN-MA (arts. 410, 412 e 413). Para o oficial: perguntar também, no Livro A, se é
sociedade simples, associação, fundação ou outra, e avisar quando a natureza diz «empresária»?

**O2. O registro no domicílio das partes (LRP art. 130) não tem como ser conferido.** O título do RTD
guarda o apresentante, mas não as partes do contrato nem o domicílio delas. Pergunta ao oficial: a casa
confere isso no balcão, no papel? Se a resposta for que deveria conferir no sistema, faltam os campos.

**CONSERTADO em 05/11/2026** (decisão do oficial, «o»): cada parte do registro tem o domicílio (cidade e UF),
informado ao incluí-la no indicador. Na ficha do RTD, um aviso confere o art. 130 com a redação da Lei
14.382/2022 — mesma circunscrição (I), a de um devedor ou garantidor quando moram em circunscrições
diversas (II), a de uma das partes sem devedor nem garantidor (III) — contra a cidade da serventia. Avisa, e
não barra: a competência é de quem qualifica. Ensaio:
`test_o_domicilio_das_partes_se_informa_e_a_ficha_confere_o_art_130`.

**O3. O registro com valor declarado (serviços 305 e 307).** O valor declarado se grava no título
(`rg_titulos.valor_declarado`), mas o item da tabela se escolhe à mão no caixa, e o valor não entra no
selo: o RTD/RCPJ sela por `atos-em-geral` (`ato_selado.caminho_do_rtdpj`). A cobertura já marca «✗ sem
teste». O ensaio não pratica isto sem saber como a tabela do TJMA cobra o RTD com valor (faixa ou
percentual), e o que o selo do TJMA espera. Pergunta ao oficial: a casa registra títulos com valor? Por
qual item?

**O4. A leitura da ficha e o ato do mesmo segundo.** **CONSERTADO em 03/11/2026**, sem depender do
oficial. O breve relato só sai se a leitura da ficha é posterior ao último ato, e a régua comparava as
horas ao segundo, com «maior que» (`atrib_certidao`, `criado_em > pj_dados_em`). No mesmo segundo, a
leitura contava como atual: o ensaio gravou os dados e dissolveu a associação no mesmo segundo, e o breve
relato saiu sem a releitura.

**O conserto não foi o `>=` que este relatório propunha**, porque ele erraria do outro lado: o registro e
a leitura logo depois dele também caem no mesmo segundo, e o breve relato seria recusado sem motivo. Agora
a leitura guarda o último ato que viu (`rg_registros.pj_dados_ultimo_ato_id`, gravado por
`rg_registro.gravar_dados_da_pj`), e a régua compara pela ordem dos atos, que não empata. A leitura
gravada antes da coluna não a tem, e segue pela hora, como era. O teste do ensaio já não espera um
segundo, e há um teste da régua só com o empate.

## Segunda leva (03/11/2026)

**Certo, e agora com teste: a associação que muda de nome sai com o nome novo no breve relato.** A
sequência é a do balcão:
- a averbação da ata da nova denominação;
- a correção do cadastro pela tela própria («Corrigir requerente», feita a pedido do oficial em 12/09/2026:
  «uma pj mudou de nome»);
- a releitura da ficha;
- o breve relato, que diz «Denominação: ASSOCIAÇÃO CULTURAL DE EXEMPLO».

## 2. A notificação se abre sobre o registro cancelado

**CONSERTADO em 03/11/2026** (sem depender do oficial, liberado pela sessão de PRs): `rg_notificacao.abrir`
recusa o registro que não está ATIVO, com a situação, o ato que o cancelou e o art. 160, antes de gravar.
O teste deixou de ser `xfail` e confere o recado.

**O que se fez.** Uma notificação extrajudicial registrada no Livro B; o registro cancelado («lavrado por
engano, a requerimento do apresentante»); depois, o pedido de notificação do mesmo título, com a
diligência paga.

**O que saiu.** «Notificação aberta. A primeira diligência vai até o prazo que a ficha mostra.»

**Por que está errado.** LRP art. 160: a notificação é a «do registro». O registro cancelado não produz
efeito (arts. 164 a 166), e a própria ficha já recusa a averbação nele («só se averba registro ativo»,
`rg_registro.lancar_averbacao`). **E o fim do caminho quebra:** a notificação, feita, se averba à margem do
registro por essa mesma função (`rg_notificacao.averbar`), que vai recusar. A casa diligencia, cobra, e só
no fim descobre que o resultado não se averba.

**Proposta.** Na abertura da notificação, a mesma régua da averbação: registro que não está ATIVO não
abre notificação, e o recado diz a situação e o ato que o cancelou.

**O5. A releitura da ficha não pergunta a denominação.** **DECIDIDO E CONSERTADO em 03/11/2026**: o
oficial respondeu «SIM», e a releitura pergunta a denominação, já preenchida com a do cadastro. O breve
relato certifica a lida (`rg_registros.pj_denominacao`). Se ela não é a do cadastro, a tela avisa e aponta
a «Corrigir requerente», porque o cadastro é o da busca e só muda com o motivo. O texto original da
observação segue abaixo. O formulário «Dados da pessoa jurídica»
(`dados-pj`) pede a sede, o objeto, o capital, os sócios e a diretoria, mas não a denominação, que o breve
relato tira do cadastro (`requerente_nome`). Quem averba a mudança de nome e relê a ficha, sem passar pela
«Corrigir requerente», certifica o nome velho, e a régua da leitura deixa (ela só confere a data). Para o
oficial: pôr a denominação no formulário da releitura, já preenchida com a do cadastro, para quem relê a
confirmar?

## O que fica para as próximas levas

- o RTD: o mesmo título registrado duas vezes (o registro facultativo, Livro F, admite; o B e o C?).

# Relatório do ensaio de atos — Registro de Imóveis (primeira leva)

Ensaio de 03/11/2026, pedido do oficial de 01/11/2026. O inventário está em `inventario_ri.md`; o teste
em `tests/test_ensaio_de_atos_ri.py`.

**Como foi feito.** `tests/test_fluxo_ri.py` já levava cada um dos 25 modelos de ato da casa da prenotação
paga à certidão, mas cada um numa matrícula limpa. Esta leva praticou **sequências na mesma matrícula**,
pelas mesmas telas e com os mesmos auxiliares de lá: protocolo pago, prenotação para a matrícula, o texto
do modelo na caixa de teor preenchido como o balcão preenche, lavratura com selo. Depois de cada sequência
se olhou o que importa a quem compra e a quem empresta: quem a certidão de propriedade diz que é dono, e o
que o pedido de certidão de ônus oferece ao escrevente para transcrever. A trava ficou ligada; a única
porta aberta foi a do selador de mentira, em 127.0.0.1.

**Resultado.** Seis sequências, todas foram ao livro com selo. Estão certos e conferidos:
- a venda com a hipoteca de pé: o dono passa a ser o comprador, e a hipoteca continua oferecida como ônus;
- a penhora averbada entra como ônus;
- o casal que compra sai inteiro como proprietário, e o vendedor sai.

Ficaram **três defeitos** no teste, em `xfail(strict=True)`, e três observações sem teste. Os dois
primeiros defeitos têm a mesma raiz.

Os nomes e os CPF são fictícios (os da lista dos fictícios). Os artigos do CNN e do CN-MA não estão nesta
máquina; onde eles pesariam, está escrito «conferir».

---

## 1. O cancelamento não tira o ônus: o pedido de certidão vem «Positiva», com o ato cancelado marcado

**O que se fez.** R-1 compra e venda; R-2 hipoteca; AV-3 cancelamento da hipoteca (modelo
AV-CANCELAMENTO-HIPOTECA), selada. Depois, o pedido de certidão de ônus na ficha.

**O que saiu.** O formulário vem com **«Positiva» marcada** e o **R-02 (Hipoteca) marcado** para
transcrição, como se a hipoteca estivesse de pé.

**Por que está errado.** LRP arts. 248 e 250: cancelado o registro, ele deixa de produzir efeito, e a
certidão de ônus (art. 19, § 9º) não o dá como vigente. O sistema deixa o escrevente desmarcar, mas o
padrão é o errado, e o erro custa: o papel faz o banco recusar o crédito, ou o comprador desistir.

**A causa.** `ri_onus.classificar` só exclui o ato com `ri_atos.cancelado`, que é o ato **tornado sem
efeito** (lavrado errado), e não o ato **baixado por averbação**. A AV de cancelamento cita o ato no texto
(«fica cancelado o registro [ATO CANCELADO]»), mas o sistema não guarda essa ligação. A situação jurídica
já tenta a mesma coisa para as fichas do acervo, procurando no teor o parágrafo de cancelamento que cita o
rótulo (`ri_situacao_juridica`, «cancelado_por»), e só avisa.

**Proposta, para o oficial decidir.** Na lavratura das averbações que extinguem um ato (cancelamento de
hipoteca ou de fiduciária, extinção de usufruto, cancelamento de penhora e de indisponibilidade, e o
AV-CANCELAMENTO), um campo «ato que se cancela», que a tela preenche a partir dos ônus vigentes da
matrícula e que se grava como ligação (`ri_atos.extinto_por_ato_id`, por exemplo). `classificar` passa a
excluir o ato extinto. O texto do modelo continua dizendo o rótulo. Pergunta: preencher a ligação também
nas matrículas já lavradas, a partir do texto das averbações, com uma lista para conferir? Ou só daqui
para a frente?

## 2. A extinção do usufruto: o usufruto continua ônus, e a própria extinção vira ônus

**O que se fez.** R-1 compra e venda; R-2 usufruto; AV-3 extinção do usufruto (AV-EXTINCAO-USUFRUTO),
citando o R-02.

**O que saiu.** O pedido de certidão de ônus oferece **o R-02 e a AV-03**.

**Por que está errado.** CC art. 1.410 e LRP art. 167, II, 2: extinto e averbado, o usufruto não pesa
mais. A averbação da extinção nunca foi ônus.

**A causa.** A mesma do item 1, para o R-02. A AV-03 entra pela palavra «usufruto» do teor, porque a
natureza «Extinção de usufruto» não está na tabela de naturezas (`CODIGOS_DE_ONUS` / `NATUREZAS`). O
cancelamento da hipoteca não entrou porque a natureza dele é reconhecida.

**Proposta.** O conserto do item 1, e as naturezas de extinção e de cancelamento na lista das que não são
ônus (`CODIGOS_SEM_SENTIDO` ou equivalente).

## 3. A indisponibilidade averbada na matrícula não barra a venda (nem avisa)

**O que se fez.** R-1 compra e venda; AV-2 indisponibilidade (AV-INDISPONIBILIDADE, ordem da CNIB
contra a proprietária); R-3 compra e venda da proprietária para um terceiro.

**O que saiu.** O R-3 foi ao livro com selo e com o recado «CNIB consultada e gravada no ato: nada consta
(cópia local)». A ficha mostrava ao mesmo tempo «Ônus: AV-02/4100».

**Por que está errado.** A indisponibilidade impede a alienação voluntária (Prov. CNJ 149/2023, arts. 500 e seguintes, como
o modelo da casa cita; LRP art. 167, II, 12). A AV-02 é a prova, no próprio livro, de que a ordem existe. A lavratura confere a
indisponibilidade só na cópia local da CNIB, que neste ensaio, como no balcão sem a base carregada, está
vazia.

**Proposta.** Na lavratura de ato de disposição (natureza de transmissão ou de oneração voluntária),
procurar na matrícula uma AV de indisponibilidade vigente (pela natureza 115 e pela ligação do item 1,
para saber se foi cancelada). Se houver, barrar, com a mesma trava que a CNIB local já usa. Pergunta: há
exceção que a casa pratica (a alienação judicial, a arrematação, que a lei admite)? A sugestão é barrar o
ato voluntário e só avisar no ato judicial.

---

## Observações (sem teste)

**O1. A certidão de propriedade não diz o estado civil do dono.** Depois da AV de casamento da
proprietária (AV-ESTADO-CIVIL), a certidão de propriedade traz o nome e o CPF, sem qualificação. A lei não
exige o estado civil nessa certidão (a de inteiro teor traz a averbação), mas quem a pede costuma querer
saber se precisa da outorga conjugal (CC art. 1.647). Para o oficial: incluir a qualificação atual do
titular?

**O2. A indisponibilidade entra como ônus «pela palavra do teor, sem natureza reconhecida — confira».**
A natureza do modelo AV-INDISPONIBILIDADE («Indisponibilidade») não casa com o nome da tabela
(«Indisponibilidade de Bens», código 115). O resultado está certo, mas o escrevente vê um aviso de
conferência que não precisaria ver. Alinhar o nome da natureza do modelo com o da tabela resolve.

**O3. A prenotação que abriu a matrícula aparece «em aberto» na certidão depois do R-1.** É a regra da
casa (`ri_web.amarrar_prenotacao`: a lavratura não encerra a prenotação; encerram o balcão e o selo de
arquivamento 16.39). Fica registrado só para o oficial confirmar que a certidão sai assim enquanto o
balcão não encerra.

## O que fica para as próximas levas

Do plano do inventário:
- a prioridade entre duas prenotações (LRP arts. 186 e 191);
- a partilha com viúva meeira e herdeiros, com as frações;
- a doação com reserva de usufruto no mesmo título;
- o desmembramento com as matrículas filhas;
- a arrematação sobre imóvel penhorado;
- o indicador pessoal e o real depois de cada sequência;
- a DOI da compra e venda.

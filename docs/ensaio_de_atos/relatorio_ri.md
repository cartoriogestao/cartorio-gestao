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
primeiros defeitos têm a mesma raiz: o cancelamento pelo modelo do «Novo ato» não liga a AV ao ato, e o
pelo botão «Cancelar este ato» liga (item 1, corrigido na segunda leva).

Os nomes e os CPF são fictícios (os da lista dos fictícios). Os artigos do CNN e do CN-MA não estão nesta
máquina; onde eles pesariam, está escrito «conferir».

---

## 1. O cancelamento pelo modelo não tira o ônus; pelo botão «Cancelar este ato», tira

**CONSERTADO em 03/11/2026** (decisão do oficial, «a1»):
- os modelos AV-CANCELAMENTO-HIPOTECA, AV-EXTINCAO-USUFRUTO e AV-CANCELAMENTO, lavrados pelo «Novo ato»,
  pedem «Qual ato se cancela» (um ato desta matrícula, de pé) antes do número;
- gravam a MESMA marca do botão, pela mesma função (`_marcar_cancelado_pela_averbacao`: `cancelado`,
  `cancelado_por_ato_id` e o lançamento de cancelamento nos indicadores). Se o selo não sai e o ato volta
  a ser minuta, a marca se desfaz pela mesma função do botão (`_desmarcar_cancelado_pela_averbacao`);
- a averbação que cancela ou extingue deixou de ser oferecida como ônus (`ri_onus.classificar`), o que
  fecha também a segunda metade do item 2;
- **as matrículas antigas:** `python ri_cancelamentos_sem_marca.py`, no servidor, lista as averbações de
  cancelamento ou extinção que não marcaram ato nenhum, com os rótulos que o texto cita e se ainda estão de
  pé. Só lê: quem marca é o oficial, pelo botão.

**CORRIGIDO em 03/11/2026, na segunda leva.** A primeira versão deste item dizia que o sistema não guarda a
ligação entre o cancelamento e o ato cancelado. **Guarda**: o botão «Cancelar este ato», na ficha, lavra a
AV e marca o R com `cancelado = 1` e `cancelado_por_ato_id` (`ri_web.ri_cancelar_ato`). Por ali, a
hipoteca e o usufruto saem do pedido de certidão de ônus, e a certidão sai «NADA CONSTA». Agora há teste
para isso (`test_pelo_botao_cancelar_este_ato_a_hipoteca_e_o_usufruto_deixam_de_ser_onus`), e
`test_fluxo_ri` já o tinha para a hipoteca. O defeito é menor do que o primeiro texto disse: **há duas
portas, e a do modelo não liga.**

**O que se fez.** R-1 compra e venda; R-2 hipoteca; AV-3 cancelamento da hipoteca pelo **«Novo ato», com
o modelo AV-CANCELAMENTO-HIPOTECA**, selada. Depois, o pedido de certidão de ônus na ficha.

**O que saiu.** O formulário vem com **«Positiva» marcada** e o **R-02 (Hipoteca) marcado** para
transcrição, como se a hipoteca estivesse de pé. O R-02 não ficou marcado como cancelado.

**Por que está errado.** LRP arts. 248 e 250: cancelado o registro, ele deixa de produzir efeito, e a
certidão de ônus (art. 19, § 9º) não o dá como vigente. O modelo está na lista do «Novo ato», e quem o usa
tem toda a razão para achar que cancelou. O sistema deixa o escrevente desmarcar no pedido de certidão,
mas o padrão é o errado, e o erro custa: o papel faz o banco recusar o crédito, ou o comprador desistir.

**A causa.** A lavratura comum (`/registro-imoveis/<id>/atos`) não sabe que o modelo cancela um ato: o
texto diz «fica cancelado o registro [ATO CANCELADO]», mas nada grava `cancelado_por_ato_id`. O botão
«Cancelar este ato» só aparece na ficha para ADMIN e MANAGER (`ri_ficha.html`), embora a rota aceite
também o escrevente (`roles_required("ADMIN", "MANAGER", "USER")`). O escrevente que lavra não vê o botão,
e vê o modelo.

**Proposta, para o oficial decidir.** Uma das duas:
- **(a1)** os modelos que cancelam ou extinguem (AV-CANCELAMENTO-HIPOTECA, AV-EXTINCAO-USUFRUTO e o
  AV-CANCELAMENTO) pedem na lavratura «qual ato se cancela», escolhido entre os vigentes da matrícula,
  e gravam a mesma marca que o botão grava;
- **(a2)** esses modelos saem do «Novo ato» e passam a ser o texto do botão.

A (a1) mantém o caminho de quem lavra. A (a2) pede também decidir quem vê o botão, porque a tela e a rota
hoje discordam. Nas matrículas
já lavradas, o que foi cancelado pelo modelo não tem a marca. Pergunta: procurar no banco as AV lavradas
por esses modelos e listar para conferir?

## 2. A extinção do usufruto: o usufruto continua ônus, e a própria extinção vira ônus

**O que se fez.** R-1 compra e venda; R-2 usufruto; AV-3 extinção do usufruto (AV-EXTINCAO-USUFRUTO),
citando o R-02.

**O que saiu.** O pedido de certidão de ônus oferece **o R-02 e a AV-03**.

**Por que está errado.** CC art. 1.410 e LRP art. 167, II, 2: extinto e averbado, o usufruto não pesa
mais. A averbação da extinção nunca foi ônus.

**A causa.** A mesma do item 1, para o R-02 (pelo botão, o usufruto sai). A AV-03 entra pela palavra «usufruto» do teor, porque a
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

## Segunda leva (03/11/2026)

Mais quatro sequências: a prioridade entre duas prenotações, a partilha, o desmembramento de imóvel
hipotecado e, conferindo o item 1, o cancelamento pelo botão «Cancelar este ato» (funciona: ver o item 1,
corrigido). **A partilha está certa:** a meeira e os dois herdeiros entram no quadro de titulares e na
certidão de propriedade, e a falecida sai. Ficaram **mais dois defeitos**, também em `xfail(strict=True)`.

## 4. O título prenotado depois passa na frente do anterior, sem aviso

**O que se fez.** R-1 compra e venda para a proprietária. Depois, duas prenotações sobre a matrícula, na
ordem: a nº 2, venda da proprietária a um comprador; a nº 3, venda da mesma proprietária a outro comprador.
A lavratura pelo protocolo 3, com a 2 ainda aberta.

**O que saiu.** O R-2 foi ao livro com selo. Os recados da tela falam da prenotação 3 («ficou amarrada a
este ato») e da CNIB. Da prenotação 2, anterior e contraditória, nem uma palavra. A ficha lista as duas
como «Aberto», mas na lista de protocolos, longe do botão de lavrar.

**Por que está errado.** LRP art. 186: o número de ordem da prenotação determina a prioridade do título, e
esta a preferência dos direitos reais. Art. 191: prevalece o título prenotado sob o número mais baixo. O
registro do título posterior, com o anterior contraditório pendente, inverte a preferência que a lei dá a
quem chegou primeiro, e quem perde é o comprador da prenotação 2.

**A causa.** A lavratura (`/registro-imoveis/<id>/atos`) amarra o ato à prenotação escolhida
(`amarrar_prenotacao`), mas não olha as outras prenotações abertas da mesma matrícula.

**Proposta, para o oficial decidir.** Na lavratura, procurar outra prenotação ABERTA da mesma matrícula com
número menor que a deste ato. Se houver: **(d1)** avisar, nomeando o protocolo, e pedir a confirmação com o
motivo (o título anterior pode ser compatível: uma hipoteca não exclui uma venda); ou **(d2)** barrar até a
anterior ser registrada, devolvida ou cancelada. A sugestão é a (d1), porque o sistema não sabe quando dois
títulos se contradizem, e o registrador sabe.

## 5. A matrícula filha aberta de imóvel hipotecado não diz nada da hipoteca da mãe

**O que se fez.** Matrícula 4.100 com R-1 compra e venda e R-2 hipoteca. «Nova matrícula» para uma área
desmembrada dela, com o registro anterior «Matrícula 4100 deste Ofício (desmembramento)».

**O que saiu.** «Matrícula 4101 aberta no livro 2.» A ficha da 4.101 não fala da hipoteca R-02/4100.

**Por que está errado.** LRP art. 230: se na certidão da origem constar ônus, o oficial abre a matrícula
e, logo em seguida ao registro, averba a existência do ônus. Sem lembrete, a filha nasce limpa na certidão
de ônus, e a garantia do credor some da publicidade da área desmembrada.

**A causa.** A abertura (`/registro-imoveis/nova`) grava o registro anterior como texto e não consulta a
matrícula de origem. A ficha já sabe achar o número dela no texto: é o que a certidão dominial usa
(`ri_dominial.sugerir_numeros_origem`).

**Proposta.** Ao abrir, e na ficha da filha enquanto não houver averbação do ônus transportado: achar a
origem pelo registro anterior (a mesma função) e listar os ônus vigentes dela, pela mesma
`ri_onus.onus_vigentes`, com o recado «averbe o transporte (LRP art. 230)». Pergunta ao oficial: só avisar,
ou também oferecer um modelo de averbação de transporte de ônus? A casa não tem esse modelo.

**O4. O quadro de titulares não guarda a fração de cada um.** Na partilha (50% para a meeira, 25% para
cada herdeiro), a certidão de propriedade traz os três nomes sem a fração. A fração está no texto do ato,
e a lei a exige lá (LRP art. 176, § 1º, III, e o quinhão do formal), mas não na certidão de propriedade.
O próprio sistema já avisa na transmissão de parte ideal («ponha de volta em Partes → Corrigir»). Para o
oficial: guardar a fração no quadro, e a certidão de propriedade dizê-la?

## Terceira leva (03/11/2026): sem defeito novo

Cinco conferências. **Todas estão certas**, e agora têm teste:

- **A doação com reserva de usufruto** (R-DOACAO e R-USUFRUTO, como o modelo manda: «objeto de registro
  próprio»): a donatária é a dona, o doador sai do quadro de titulares, e o usufruto entra como ônus. A
  doação não entra.
- **O indicador pessoal (LRP art. 180)**, depois de duas vendas: o primeiro vendedor e a compradora que
  revendeu continuam achados na matrícula, com o papel; só o casal que comprou por último aparece como
  «Proprietário atual».
- **A DOI do mês** (Lei 10.426/2002, art. 8º), na tela do oficial: as duas vendas, cada uma com quem aliena
  e quem adquire. Nenhuma entra enquanto falta o que a Receita pede: o tipo da operação, o valor, a base do
  ITBI e a participação de cada adquirente, que no casal é obrigatória. A tela diz que o que falta se
  digita na CTP. (A tela da DOI dá 403 ao escrevente, o USER; é do oficial, como a remessa.)
- **O prazo da prenotação (LRP art. 205):** a prenotação de 03/11/2026 vence em 02/12/2026, 20 dias úteis
  contados sem o 20/11 (feriado nacional), como manda a contagem em dias úteis da LRP depois da Lei
  14.382/2022. Conferido na ficha, sem teste novo: `ri_prenotacao_prazo` já tem os dele.

- **A arrematação sobre imóvel penhorado** (CPC arts. 901 e 903): o arrematante é o dono e a executada
  sai; a penhora continua oferecida como ônus. É o certo: o registro não se cancela sozinho (LRP arts. 250
  e 251), e o mandado de cancelamento se averba pelo botão «Cancelar este ato», que funciona.

## O que fica para as próximas levas

Do plano do inventário, o RI está praticado. Ficam fora do ensaio, porque precisam de rede ou de dados de
fora: o pedido pela ONR, a CNIB central e a consulta à CNM. Os consertos esperam as respostas do oficial
às perguntas (a) a (f).

# Relatório do ensaio de atos — Tabelionato de Protesto (primeira leva)

Ensaio de 03/11/2026, pedido do oficial de 01/11/2026. O inventário está em `inventario_protesto.md`; o
teste em `tests/test_ensaio_de_atos_protesto.py`.

**Como foi feito.** `tests/test_fluxo_protesto.py` já leva cada ato do protocolo pago ao papel, sempre com
o mesmo título: nota promissória, protesto comum por falta de pagamento, devedor pessoa física. Esta leva
praticou, pelas mesmas telas e com os mesmos auxiliares de lá, o que muda o ato:
- o motivo (falta de aceite);
- a espécie (cheque);
- o mesmo título apresentado duas vezes;
- o devedor pessoa jurídica;
- dois protestos do mesmo devedor, com um cancelado.

O caminho de cada título é o do balcão: cadastro em `/protesto/novo`, apontamento, aviso entregue em mãos
com o canhoto, protesto pela ficha. A trava ficou ligada; a única porta aberta foi a do selador de
mentira, em 127.0.0.1.

**Resultado.** Estão certos e conferidos:
- dois protestos do mesmo devedor, com um cancelado pela anuência: a certidão a terceiro é POSITIVA e traz
  só o que está em pé;
- a empresa devedora: a certidão pelo CNPJ é POSITIVA, e a de outra pessoa, NEGATIVA.

Ficaram **três defeitos**, em `xfail(strict=True)`, e duas observações. Os três são do mesmo tipo: o
balcão aceita um título que o tabelião teria de recusar ou, no mínimo, conferir, e a tela não diz nada. A
CRA já traz o vocabulário dessas recusas (`protesto_cra`, irregularidades 52, 53 e 54). O título que vem
pelo balcão não passa por ele.

Os nomes e os documentos são fictícios. Os textos da Lei 9.492/1997, do CNN e do CN-MA não estão nesta
máquina: os artigos são os que `docs/REQUISITOS_LEGAIS.md` cita, e onde o código de normas pesaria está
escrito «conferir».

---

## 1. O mesmo título se protesta duas vezes

**O que se fez.** A nota promissória NP-0001, do mesmo credor contra o mesmo devedor, no mesmo valor,
cadastrada pelo balcão, apontada, intimada e protestada. Depois, o mesmo título outra vez, do começo.

**O que saiu.** «Título NP-0001 cadastrado», «Apontamento lançado. Livro 1, fl. 1, nº 2», «Protesto
lançado. Livro 1, fl. 1v, nº 2». Nenhum aviso. O devedor tem dois protestos de uma dívida só.

**Por que está errado.** Lei 9.492/1997, art. 9º: o tabelião examina os caracteres formais do título, e o
apresentado em duplicidade não se protesta. A própria CRA tem as recusas: «Título apresentado em
duplicidade» (52) e «Título já protestado» (53).

**Proposta, para o oficial decidir.** No cadastro e no apontamento, procurar título da mesma espécie e
número, com o mesmo credor e o mesmo devedor (pelo documento), que esteja apontado, intimado ou
protestado. Se houver: **(g1)** barrar, com o protocolo e a situação do outro; ou **(g2)** avisar e pedir
a confirmação com o motivo. A sugestão é a (g1) para o protestado e a (g2) para o apontado, porque o
segundo pode ser a reapresentação de um título retirado.

## 2. O protesto por falta de aceite se lavra depois do vencimento

**O que se fez.** Uma duplicata por indicação (DMI), vencida em 10/02/2025, com o motivo «2» (falta de
aceite), pelo mesmo caminho.

**O que saiu.** O protesto se lavrou, e o registro diz «PROTESTO COMUM LAVRADO POR FALTA DE ACEITE».

**Por que está errado.** Lei 9.492/1997, art. 21, § 1º: o protesto por falta de aceite «somente poderá
ser efetuado antes do vencimento da obrigação». § 2º: depois do vencimento, «o protesto sempre será
efetuado por falta de pagamento». O registro afirma um motivo que a lei não admite naquela data.

**A causa.** O motivo vem do cadastro e vai ao termo como está (`protesto_termo.motivo_no_livro`). Nada
compara o motivo com o vencimento.

**Proposta.** Na lavratura: motivo de falta de aceite com vencimento anterior à data do protesto, ou
barra com o artigo, ou troca para falta de pagamento, como manda o § 2º, avisando a troca. Pergunta ao
oficial: qual das duas? A lei diz «sempre será efetuado por falta de pagamento», o que sugere a troca. A
mesma regra vale para a falta de devolução (§ 3º): conferir.

## 3. O cheque se protesta sem a prova da apresentação ao banco

**O que se fez.** Um cheque (CH), pelo balcão, até o protesto.

**O que saiu.** Protesto lavrado, sem nenhuma pergunta sobre a apresentação ao banco sacado. A ficha não
tem campo para ela (banco, alínea da devolução, data). No sistema, «cheque» só existe como forma de
pagamento.

**Por que está errado.** Lei 9.492/1997, art. 6º: no protesto do cheque, «deve dele constar a prova de
apresentação ao Banco sacado», salvo se o protesto tiver por fim instruir medida contra o próprio banco.
O CN-MA tem regra própria do cheque (as alíneas que impedem o protesto, como a de furto ou extravio):
**conferir**.

**Proposta.** Na ficha do cheque, os campos «banco sacado», «alínea da devolução» e «data da
apresentação», obrigatórios para lavrar, salvo marcando que o protesto é contra o banco. O registro e o
instrumento os dizem. Pergunta ao oficial: a casa recebe cheque pelo balcão? E quais alíneas o CN-MA
proíbe?

---

## Observações (sem teste)

**O1. O protesto para fins falimentares contra CPF se lavra sem aviso.** A Lei 11.101/2005 só alcança
empresário e sociedade empresária (art. 1º), mas o empresário individual também usa CPF, e o sistema não
tem como saber. Fica a pergunta: avisar, no tipo F com CPF, «confira se o devedor é empresário»? Sobre a
intimação por edital do protesto falimentar, a CRA tem a recusa «Vedada a intimação por edital para
protesto falimentar» (69), e a Súmula 361 do STJ exige a identificação de quem recebeu a intimação. O
ensaio não chegou ao protesto por edital, porque o edital digitado à mão é barrado antes (regra geral,
certa). Fica para a próxima leva, com o edital publicado pela tela.

**O2. O devedor falecido.** A CRA tem a irregularidade «Pagador Falecido» (59). Pelo balcão não há onde
dizer isso. Fica para a próxima leva, com a pergunta ao oficial sobre como a casa procede (intimação do
espólio, conferir o CN-MA).

## O que fica para as próximas levas

- a falta de devolução (motivo 3);
- o título em moeda estrangeira (art. 10);
- o protesto falimentar com edital publicado;
- o devedor falecido;
- a gratuidade, que a cobertura marca como sem teste.

# Roteiro da 3.6.28 — as quatro decisões que você tomou em 28/08

Você pediu para eu perguntar tudo o que travava, e respondeu quatro coisas. Esta versão
é a resposta às quatro, mais um defeito que apareceu no caminho e um item de layout que
você tinha relatado.

---

## 1. «Campo por parte, sugerido em partes iguais e editável» — a DOI

**Onde:** na ficha da escritura, no painel *O imóvel — para a DOI*.

O painel agora lista **as partes do ato**, dizendo de que lado cada uma está na
declaração — *alienou*, *adquiriu*, *não é parte do negócio*, ou **não dá para saber o
lado** — e traz o percentual de participação **já preenchido** com a divisão igual.

Mostrar o lado ali não é enfeite: é como quem lavra descobre, ainda na ficha, que
escreveu «Declarante» onde precisava de «Vendedor» — em vez de descobrir no fim do mês,
na tela da DOI.

**A recusa é no balcão.** Se a soma de um lado sair fora de 99% a 100%, a tela recusa e
diz por quê, com o cliente ainda na frente. A Receita recusaria o **arquivo inteiro**, e
não a linha — descobrir isso no fim do mês custa o prazo da serventia.

> **E dois defeitos apareceram medindo isso.** As colunas `doi_transacao` e
> `doi_tipo_imovel` são numéricas: a tela grava `"11"`, o banco guarda `11`. A caixa de
> seleção comparava texto com número e **nunca voltava marcada** — você escolhia «Compra
> e venda», gravava, reabria a ficha e via «— não informada —», como se não tivesse
> gravado. E a coluna «Operação» da tela da DOI mostrava **`11`** em vez do nome.

---

## 2. «Proprietário é o dono de registro, e não necessariamente quem transferiu»

Confirmado no código: quando a qualificação da parte diz «Proprietário(a)», a escritura
**para e pergunta**, em vez de mandar aquela pessoa à Receita como quem vendeu.

Foi a escritura 222 desta casa que decidiu: nela o `Proprietário(a)` aparece **ao lado**
de um `Vendedor(a)` e de dois compradores. Se o proprietário fosse o vendedor, o vendedor
não estaria ali.

---

## 3. «Avisar e preparar a averbação, ficando pendente okay do cartório» — o CNIB

**Onde:** *Registro de Imóveis → CNIB — o que espera seu okay.*

Cada linha é uma ordem de indisponibilidade que atinge parte de matrícula desta casa, com
**a averbação já redigida** — protocolo, data, juízo e processo no lugar. Dois caminhos:
abrir a matrícula para averbar, ou dizer que **não é a mesma pessoa**, com o motivo
escrito.

O sistema **não averba sozinho**, e o motivo é medido: das 50.054 pessoas do CNIB,
**nenhuma** bate por CPF com parte de matrícula desta casa, e **seis batem por nome** —
«Pessoa Exemplo», «Pessoa Exemplo» —, com ordens do TJSC, do TJPR, do
TRF6 e de uma vara do Rio Grande do Sul. Averbar em cima de um homônimo tira de um
inocente o direito de dispor do imóvel dele, e isso só sai por ordem de cancelamento.

> ### E o alerta do CNIB nunca havia aparecido para ninguém
>
> Construindo essa lista, apareceram **dois defeitos** na busca que a ficha da matrícula
> usa. Cada um bastava sozinho para a busca por nome nunca devolver nada:
>
> 1. **a exclusão olhava a tabela toda** em vez do que se procurou — e como todas as
>    50.054 pessoas do CNIB têm documento, a busca por nome devolvia lista vazia sempre;
> 2. **o `UPPER` do banco não mexe em acento** — «José» de um lado nunca encontrava «JOSE»
>    do outro, e há **1.257** nomes acentuados nas partes das matrículas.
>
> Com os dois de pé, o aviso só podia sair por documento — e por documento o número de
> achados é zero. **A tela avisava, e nunca teve o que avisar.**
>
> Corrigido, a lista saiu de **22,5 segundos e zero achados** para **0,1 segundo e dez**.

---

## 4. «Eu monto do Código de Normas do TJMA e da lei, e você confere» — o usucapião

**Onde:** *Registro de Imóveis → Usucapião — o que o Código de Normas exige.*

**O Código estava na sua pasta de Downloads** — `Código de normas TJMA atualizado.pdf`,
249 páginas. A Seção XIV, arts. 747 a 761, é a usucapião extrajudicial. Li e transformei
em regra, cada uma com o artigo do lado, para você abrir o PDF e conferir.

O que faltava era o **direito estadual inteiro**: onze dos doze itens do checklist citavam
a Lei de Registros Públicos, e o único que citava o Código dava a faixa toda sem dizer o
quê. Entraram, entre outros:

- **a justificação do óbice (art. 748)** — a pergunta que separa a usucapião da compra e
  venda que ninguém quis registrar para não pagar ITBI, com as sete hipóteses do § 1º e o
  alerta de que declaração falsa é crime;
- **o conteúdo da planta (art. 753)** — perímetro, configuração geométrica, coordenadas
  UTM SIRGAS 2000, e a identificação de cada confrontante com livro, folha e serventia;
- **as quatro respostas de área contra matrícula** (§§ 2º a 4º), cada uma levando o
  registro a um lugar diferente;
- **o que não impede** — imóvel sem registro, área menor que a fração mínima, ônus na
  matrícula, indisponibilidade posterior à posse. É a lista que evita um balcão inseguro
  travar um pedido bom;
- **os três deveres quando há indisponibilidade (art. 760)**, que acontecem em momentos
  diferentes do rito — e o do meio é o único que pode indeferir o pedido;
- **o prazo do edital (art. 755)**, que tem **dois saltos e não um**.

> **E eu quase gravei uma correção errada.** O código citava «arts. 747 a 761» e eu escrevi
> que a faixa terminava no 760, porque foi até ali que li. Fui conferir antes de deixar a
> frase de pé: a Seção XV só começa no **762** — o 761 é de usucapião, e trata do imóvel
> edificado. **A citação que já estava no código estava certa.**

---

## 5. O layout que você relatou

*«Layout das caixas de seleção muito separadas, falta listras nas tabelas.»*

As tabelas ganharam listra nas linhas pares, e os campos dos formulários ficaram mais
juntos — eram 18 pixels entre campos, agora são 11. Num formulário de dez campos, isso
tirava metade deles da tela.

---

## Como aplicar

1. Feche o sistema nas máquinas do balcão.
2. Rode **`ATUALIZAR_SISTEMA.cmd`**.
3. Abra o sistema e confira, no rodapé, que diz **3.6.28**.
4. Abra *Registro de Imóveis → CNIB — o que espera seu okay*: com o banco de produção,
   ele deve listar **dez** ordens, todas achadas por nome.

O banco migra sozinho ao subir. A coluna nova do CNIB (`nome_norm`) é preenchida na
subida, de uma vez, para as 50.054 pessoas — leva menos de um segundo.

---

## O que continua esperando você

- **rodar a carga do acervo**, marcando o IBGE;
- **os quatro cliques da configuração do selador**;
- trocar a senha do selador com a FPFTech/TJMA;
- perguntar à FPFTech se o serviço de selo devolve o token do QR.

E do backlog do balcão continuam abertos: encerrar protocolo, pré-visualizar matrícula com
o ato novo, rascunho de ato sem consumir número, layout da certidão de inteiro teor e o
AV-28 no teor de ficha do acervo.

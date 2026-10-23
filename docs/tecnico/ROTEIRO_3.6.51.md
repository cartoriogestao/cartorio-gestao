# Roteiro da 3.6.51 — cada registro civil na sua tela

**Basta este pacote.** Ele exige a 3.3.0 e inclui tudo o que já vinha nas
atualizações anteriores.

## O que mudou

O formulário único do Registro Civil foi substituído por uma porta de escolha
e por telas próprias para cada espécie. Nascimento, casamento, casamento
religioso, óbito, natimorto, proclamas e cada registro do Livro E têm agora uma
URL fixa. A espécie escolhida define o livro no servidor e não pode ser trocada
pela edição do formulário.

As telas seguem a organização vista nos prints do E-Ofício:

- **nascimento:** registrado, filiações, progenitores, declarante,
  testemunha, dados do nascimento e DNV;
- **casamento:** dois nubentes, filiações de cada um, testemunha, habilitação,
  regime de bens e dados da celebração;
- **óbito:** falecido, filiações, declarante, testemunha, dados do óbito e DO;
- **espécies auxiliares e Livro E:** apenas os blocos admitidos pelo domínio,
  sem reaproveitar campos de nascimento, casamento ou óbito.

Filiações, progenitores, declarante e testemunha ficam em blocos recolhíveis.
O titular do registro fica aberto. Os progenitores do nascimento pedem apenas
o nome, como cabe ao termo, em vez de repetir profissão, estado civil e
endereço. O recém-nascido também não recebe campos de profissão ou estado
civil.

## Averbações, anotações e retificações

Há uma entrada própria **Registro Civil → Averbações**, com busca por nome ou
matrícula. Depois de escolher o assento, a tela de averbação mostra somente:

- resumo do assento;
- teor;
- fundamento;
- selo e cobrança.

A ficha do assento deixou de empilhar três formulários. Ela agora oferece três
portas distintas: averbação, anotação e retificação. A retificação continua
exigindo fundamento; nenhuma dessas operações ocupa folha nova.

## Compatibilidade preservada

- importações antigas que chegam pela rota geral são encaminhadas à espécie
  correta sem perder os valores;
- integrações que ainda fazem `POST /rcpn/novo` continuam aceitas;
- o nome principal passa a vir do registrado, do falecido ou dos dois
  nubentes, sem duplicar a pergunta na tela;
- casamento religioso passou a aceitar os mesmos dados de celebração do
  casamento civil.

## Como conferir

1. Veja **3.6.51** no rodapé.
2. Abra **Registro Civil → Assentos → Assento novo** e confirme os cartões de
   cada espécie.
3. Abra nascimento, casamento e óbito e confira que DNV, regime de bens e DO
   não aparecem fora do registro a que pertencem.
4. Abra **Registro Civil → Averbações**, localize um assento e confira a tela
   exclusiva do lançamento.

Os testes automatizados conferem também que adulterar a espécie enviada por
uma tela de nascimento não consegue deslocar o registro para o Livro C.

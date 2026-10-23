# Roteiro da 3.6.26 — seis débitos do balcão, pagos

*Serventia Extrajudicial de Cidade Exemplo/MA, CNS 000000 — 28/08/2026*

**2.458 testes, todos passando.** O pacote é `CartorioGestao_3.6.26.cgu`,
SHA-256 `34ef347ef94a20df896280e85885957856b667b21da866595967a0455aa66fc0`.

> **Ela inclui a 3.6.23, a 3.6.24 e a 3.6.25.** Aplique só esta.

---

## Cada débito foi medido antes de ser consertado

Nenhum destes era suspeita. Todos vieram com número.

### 1. Cancelar certidão tinha rota e não tinha botão

Varri as **143 rotas do sistema que gravam** e comparei com as telas: **uma** não
era chamada por nenhuma.

Uma certidão do Registro de Imóveis emitida por engano — matrícula errada,
requerente trocado — ficava válida no mundo, com o sistema sabendo cancelá-la e
ninguém podendo mandar.

Agora tem botão, com motivo obrigatório. E há um teste que **varre isso
continuamente**: se aparecer rota órfã nova, ele fica vermelho. Era o defeito que
mais se repetiu neste projeto — seis vezes —, e agora ele tem alarme.

### 2. O caixa não dizia quem fechou, e a conferência não existia

Medido: `fechado_por` NULL em **2.755 de 2.755** caixas fechados, e
`conferido_por` NULL em **2.758 de 2.758**.

O segundo não era campo esquecido: era um **ato que não existia**. Fechar e
conferir são coisas de duas pessoas — quem atende fecha o próprio caixa e conta o
próprio dinheiro; quem confere é você, depois.

Agora há um painel na tela do caixa com os fechados esperando conferência, **e
ele nunca mostra o seu próprio**. Se conferisse a si mesmo, a conferência não
valeria nada — o sistema recusa, com essa frase.

### 3. A prenotação não se amarrava ao ato

Medido: `ri_protocolos.ato_id` vazio em **784 de 784**.

Isso não é cadastro: é **prioridade** (Lei 6.015/1973, art. 186). Quando dois
títulos disputam o mesmo imóvel, a pergunta é qual prenotação veio antes **e qual
ato saiu dela** — e a segunda metade se respondia comparando datas à mão.

Agora o campo «Protocolo» oferece as prenotações abertas, e lavrar o ato
**encerra e amarra** a prenotação. Com três recusas:

- protocolo que não existe **não derruba o ato**, mas a tela avisa;
- prenotação já amarrada **continua no primeiro ato**: prioridade não se
  transfere;
- prenotação cancelada não reabre.

### 4. A marca REURB-S era lida e jogada fora

A tela perguntava, calculava os 40 dias úteis em vez de 20 — e não guardava a
resposta. O prazo ficava sem dizer por quê, e numa correição a pergunta é
exatamente essa. Agora a ficha diz: *«REURB-S, e é por isso que o prazo é de 40
dias úteis e não de 20»*.

### 5. O recibo da DOI dizia sucesso sem remessa

O comando que registra o recibo **não conferia se existia remessa** daquela
competência. Sem ela, ele mudava zero linhas — e a tela dizia «Recibo da DOI
registrado» do mesmo jeito.

O escrevente ia embora achando que a obrigação estava cumprida. **A DOI tem multa
da Receita Federal.**

Agora o sistema pergunta ao banco quantas linhas mudaram e, se nenhuma, diz o que
houve. E recibo **sem número** é recusado: recibo sem número não prova entrega.

---

## 6. O CNM — e este merece um parágrafo à parte

O Código Nacional de Matrícula estava guardado em 1.656 matrículas e o sistema
**nunca o gerou nem conferiu**.

Olhando os seis primeiros do acervo, o padrão apareceu: cada +1 no número da
matrícula dá **−3** no dígito. Isso é a assinatura do módulo 97.

Testado contra os **1.656 códigos reais**: **1.656 certos, zero errados.** É
**ISO 7064 MOD 97-10**, o mesmo algoritmo do IBAN.

```
000000 . 2 . 0000001 - 98
  CNS   livro  número    DV
```

O sequencial **é** o número da matrícula (1.656 de 1.656), e o dígito do livro é
o **número** do livro, não a letra do volume — `2A`, `2S` e `2C` são todos `2`.

### Por que aqui se gera e no Registro Civil não

A matrícula de 32 dígitos do RCPN **não** se gera: 243 amostras testadas contra
módulo 11 em quatro conjuntos de pesos, duas convenções e dez mapeamentos, mais
módulo 97 e Luhn — o melhor acertou **46 de 243**, nível de acaso.

Aqui é um algoritmo público que reproduz **todos** os números que a casa já
emitiu. **Gerar é reproduzir o que já existe; lá seria inventar.**

### O que muda

Toda matrícula nova nasce com o código — e **duas lavradas por este sistema
estavam sem ele**, junto com 43 antigas que o E-Ofício não trouxe.

Nas antigas, a ficha **mostra o código calculado**, marcado como «calculado,
ainda não gravado», com um botão para gravá-lo. Não gravei sozinho de propósito:
o código é derivado e conferível, mas quem assina o registro é você.

E se o CNS da serventia não estiver informado, a matrícula **sai do mesmo
jeito**, sem o código: ele é identificação, e não pode travar a abertura de um
registro.

---

## Os passos

**1. Feche o sistema.** **2. Faça o backup.** **3. Aplique o `.cgu`.**
**4. Confira que `VERSAO.txt` diz 3.6.26.**

**5. Rode a carga do acervo**, marcando tudo — os números a conferir estão no
`ROTEIRO_3.6.25.md`.

**6. Abra uma matrícula qualquer** e veja o CNM. Nas 43 antigas sem ele, o código
aparece calculado com o botão «gravar» ao lado.

**7. Abra a tela do caixa.** Se houver caixa fechado de outro operador, ele
aparece esperando conferência.

---

## O que sobra do backlog

Encerrar protocolo · pré-visualizar matrícula com o ato novo · rascunho de ato
sem consumir número · layout da certidão de inteiro teor · AV-28 aparecendo no
teor de ficha do acervo (medido: **14 de 400** matrículas repetem, no teor da
ficha, atos que já existem como linha própria).

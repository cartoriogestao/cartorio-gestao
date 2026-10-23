# Roteiro da 3.6.33 — a ajuda passa a saber do projeto

**Arquivo:** `CartorioGestao_3.6.33.cgu`
**SHA-256:** `32f5a0d0079699f5fb01b6b2fe2ae2bf54271220213237bb36249a28fea03802`
**Testes:** 2.682 passaram, 8 puladas.

Responde ao **relato #26**:

> «melhorar as capacidades da resolução de problemas. Precisa poder permitir,
> caso preciso, acesso a mais informações, inclusive acesso ao projeto do
> sistema para saber o que já foi feito, o que falta.»

*(Traz também a 3.6.32, do relato #28 — os modelos de todos os papéis da casa.
Ver `ROTEIRO_3.6.32.md`: se você ainda não aplicou aquela, esta a inclui.)*

---

## O que muda no seu dia

**Administrativo → Ajuda → O que a ajuda sabe do projeto**

Ela mostra, sem perguntar nada e **sem gastar consulta**:

- a versão em que a casa está;
- os **80 documentos do projeto**, com o que cada um é — e você pode ler
  qualquer um ali mesmo;
- os **relatos** que você abriu, com o número de cada um;
- as **pendências que só você pode informar**;
- e, no fim, **o texto exato que sai** quando você pede à ajuda para ler um
  problema.

E quando você clicar em **«ler o problema»** na tela dos problemas, tudo isso vai
junto da pergunta. Antes ela lia o defeito sem saber em que versão a casa está,
o que já foi consertado nem o que espera decisão sua — lia no escuro.

---

## Três coisas que você precisa saber

### 1. O servidor não tinha um único documento do projeto

A ajuda roda no servidor, e **nenhum dos documentos chegava lá**. Eles estavam em
**duas pastas** — 67 na raiz do projeto e 13 dentro da pasta que é empacotada —,
e só a de dentro viaja. Nem eram cópias: eram **duas metades**, e o índice citava
as duas como se fossem uma.

Consolidados: **80 documentos** na pasta que viaja, nenhum sobrescrito. Os 67
antigos ficaram onde estavam, com um aviso — **apagar documentação é decisão
sua**, e quando você mandar eu apago.

### 2. Nove pendências suas estavam caladas

Eu escrevi a função que lista as suas pendências chamando o nome errado, e um
tratamento largo de erro transformava isso em **«zero pendências»** — com cara de
medição. São **nove**, e são estas:

- a letra da posição 566, para apresentante novo;
- o Livro 6 de Apontamento, aberto e nunca usado;
- o próximo número do Livro de Protocolo do Protesto;
- o próximo número do Livro de Registro de Pagamentos;
- o próximo número do Livro de Registro de Protestos;
- os casamentos do segundo grupo são do Livro B-Auxiliar?;
- o próximo número do Livro B-Auxiliar;
- o próximo número do Livro C-Auxiliar;
- e a nona, que a tela mostra.

Agora, se algo falhar ao medir, a tela **diz que falhou** em vez de mostrar zero.
**Zero medido e zero por engano são a mesma tela e coisas diferentes.**

### 3. Ela vai dizer «28 em aberto», e você tem 24 consertados

Os dois estão certos. **A situação é o que você marcou na tela** — eu não marco
nada como resolvido, porque esse clique é seu. Sem uma frase explicando isso, a
ajuda responderia *«você tem 28 problemas em aberto»* com toda a convicção.

A frase vai junto do número, sempre. E quando quiser fechar os que já estão
resolvidos, é em *Problemas do sistema*, um a um.

---

## Os passos

1. **Faça o backup** antes de atualizar.
2. Rode `ATUALIZAR_SISTEMA.cmd`.
3. Confira em *Administrativo → Atualizações* que diz **3.6.33**.
4. Abra *Administrativo → Ajuda → O que a ajuda sabe do projeto*. Deve listar
   **80 documentos** e **nove pendências**.
5. Abra *Administrativo → Modelos dos documentos* (veio na 3.6.32) e confira que
   lista **nove papéis**, todos em «padrão do sistema».

**Nada muda na aparência de nenhum papel**, e nada precisa ser configurado.

---

## O que continua pendente

- **A carga do acervo ainda não rodou** — *Livros e acervo → Trazer o acervo do
  E-Ofício*. Enquanto ela não rodar, Protesto, RCPN, RCPJ/RTD e Livro 3 estão de
  pé e vazios, e **nenhum contador foi semeado**.
- **Os quatro cliques da configuração do selador**, que são seus.
- **A senha do selador**, com a FPFTech ou o TJMA.
- **Perguntar à FPFTech** se o selador devolve o token dos selos novos — relato
  #16.
- **O certificado do selador venceu em 10/11/2025.** Não impede de selar; você
  pediu para ser lembrado.
- **Um arquivo vazio ficou em `C:\ProgramData\CartorioGestao\cartorio.sqlite3`.**
  Fui eu que criei, por engano, ao apontar para o nome errado do banco — o banco
  de verdade é `cartorio_gestao.sqlite3` e **não foi tocado**. O vazio pode ser
  apagado; eu tentei e o sistema não me deixou apagar arquivo naquela pasta.

---

## E o que vem agora

Você decidiu criar o **módulo de retificação de área e georreferenciamento**, e
mandou levar em conta o Código de Normas do TJMA. Já li e medi as três seções —
**arts. 587 a 620** —, e está em `RETIFICACAO_NO_CODIGO_DE_NORMAS.md`, com o
artigo ao lado de cada regra, para você conferir antes de eu construir.

O desenho do módulo e o do **expediente que se abastece sozinho** estão em
`DESENHO_INACABADOS_E_RETIFICACAO.md`.

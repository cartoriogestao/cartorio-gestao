# Roteiro para aplicar a versão 3.6.15

Substitui os roteiros da 3.6.0 à 3.6.14, que ficam como registro do que cada um
trazia.

> ## Aplicada em 27/08/2026, às 08h41
>
> Você aplicou pelo `ATUALIZAR_SISTEMA.cmd`. Conferido no mesmo dia: o servidor
> responde **3.6.15**, os arquivos batem com os do projeto, o banco migrou
> sozinho e o dado antigo está inteiro.
>
> **Falta o passo 5 — rodar a carga do acervo.** As quatro atribuições novas
> estão de pé e vazias, e nenhum contador foi semeado. É o que impede o defeito
> de 18/08 de voltar no primeiro ato novo.
>
> **O uso do sistema continua suspenso desde 18/08/2026** — não há ato novo na
> auditoria. Nada aqui muda isso; quem decide voltar a lavrar é você.

---

## O que esta versão traz

**A ajuda passou a existir em todas as telas**, como você pediu em 26/08/2026 —
e passou a saber do sistema, a saber dos problemas e a escrever o relatório do
que precisa de conserto.

### 1. A janela, em qualquer tela

No canto de baixo, à direita, em **toda** tela do sistema: um botão *"Ajuda
desta tela"*. Ele abre uma gaveta por cima do que você está fazendo — sem
recarregar a página e **sem apagar o que já estava preenchido**.

Era esse o ponto: antes, tirar a dúvida custava sair do ato pela metade.

**Ela já sabe de que tela você está falando.** Não é preciso explicar "estou na
ficha do título": a pergunta sai com a tela, o arquivo e as tabelas daquela
parte do sistema.

### 2. Ela conhece este sistema, e não "cartório" em geral

Junto de cada pergunta vai o **mapa desta instalação**, medido na hora: as 218
telas com o nome que elas têm **no seu menu**, o arquivo onde cada uma mora, e as
105 tabelas do banco desta máquina.

Isso é o que faz a diferença entre *"procure na tela de registro"* e *"é em
Demais atribuições → Registro Civil — assentos, no endereço /rcpn"*.

**Nenhum dado de cliente vai junto**: vão nomes de tela, de arquivo e de coluna,
nunca o conteúdo delas. Há teste que põe CPF, nome e endereço num banco e procura
os três no que sai.

### 3. O sistema anota sozinho o que dá errado

Quando uma tela quebra, o escrevente passa a ver uma página que diz **o que fazer**
— "nada foi gravado pela metade; se era um ato, refaça" — em vez do erro cru. E o
defeito **fica anotado sozinho**, com a hora, a tela, quem estava e o ponto exato
do programa onde parou.

Antes disso, o único registro era a lembrança de quem estava no balcão. Em dia de
movimento, é o que se perde primeiro.

**E quem quiser contar, conta.** A janela tem *"Avisar um problema desta tela"* —
para o botão que não faz nada e o número que sai errado, que são justamente os
defeitos que máquina nenhuma percebe. **Isso qualquer um do balcão pode fazer**,
mesmo sem a ajuda liberada para o perfil dele: avisar não gasta e não manda nada
para fora.

### 4. A lista, a conferência e o relatório

Nova tela: *Administrativo → **Problemas do sistema*** (você e o gerente).

| Botão | O que faz |
|---|---|
| **Conferir a casa** | mede o que o sistema já sabe medir: se o banco travou, se a integridade está boa, o que falta você informar, se a manutenção diária terminou, se a ajuda ficou sem responder |
| **Pedir a leitura da ajuda** | pergunta à IA o que ela vê naquele problema — o que provavelmente aconteceu, o que fazer agora, e onde olhar. É **conselho**, e fica marcado como tal |
| **Gerar o relatório para conserto** | monta um arquivo de texto com tudo, para mandar a quem cuida do sistema |

O relatório **sai sempre com CPF e telefone mascarados** — ele nasce para deixar
a serventia. Ele baixa e **também fica guardado** na máquina, em
`%PROGRAMDATA%\CartorioGestao\relatorios\`.

Cada problema no relatório traz **o arquivo do programa onde a tela mora**,
medido nesta instalação. É por ali que quem for consertar começa.

---

## Duas coisas que ela continua não fazendo

**Ela não conserta nada, e não decide nada.** Lê, explica e escreve o relatório;
o conserto é de quem programa, com o código na frente. Há teste que varre o
código procurando função que conserte, e ele fica vermelho se alguém acrescentar
uma.

**O relatório não se manda sozinho.** Quem decide mandar, e para quem, é você.

---

## O que continua igual

- **A chave da API não entra no banco** — `%PROGRAMDATA%\CartorioGestao\claude.cred`.
- **CPF e telefone saem mascarados por padrão**, e a tela mostra o que sairia
  antes de sair.
- **O teto de 120 consultas por dia** continua valendo, e continua sendo o que
  segura um erro que repita a chamada sozinho.
- **Perguntar** continua liberado só para você, com a opção de expandir em
  *Administrativo → Ajuda — configurar*.

---

## Um defeito que esta versão conserta

A tela que mostra uma consulta antiga da ajuda dava **erro do sistema** quando
quem a abria não tinha perfil para isso — em vez de dizer "não está liberado
para o seu perfil". Ninguém tinha esbarrado nisso porque só você usava a ajuda,
e para você ela nunca recusa.

---

## Os seis passos

### 1. Parar o serviço

```bat
net stop CartorioGestao
```

### 2. Guardar o banco

```bat
copy "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3" "%PROGRAMDATA%\CartorioGestao\cartorio_gestao-antes-da-3.6.15.sqlite3"
```

> **O nome do arquivo estava errado nos roteiros anteriores** — eles mandavam
> copiar `cartorio.sqlite3`, e o banco desta casa se chama
> `cartorio_gestao.sqlite3`. O `copy` não achava o arquivo, escrevia uma linha
> de erro e o roteiro seguia como se a cópia tivesse sido feita.
>
> **Cópia que falha em silêncio é pior que cópia nenhuma**: quem seguiu o
> roteiro acha que tem para onde voltar. Corrigido aqui em 27/08/2026.

**Não pule este passo.** Esta versão acrescenta **duas tabelas** — `aj_problemas`
(o que quebrou) e `aj_relatorios` (os relatórios que saíram) — e mais nada. As
duas entram sozinhas ao abrir o banco, e **nenhuma apaga nada**. A cópia é o
caminho de volta se algo não parecer certo.

Se você ainda não aplicou a 3.6.14, esta versão traz tudo o que ela trazia — a
certidão do Registro Civil no modelo do CNJ, os pais e os avós na carga, e as
outras duas tabelas (`rc_certidoes` e `rc_pessoas`) mais as quatro colunas de
`rc_assentos`. O roteiro daquela versão fica em `ROTEIRO_3.6.14.md`.

### 3. Conferir o pacote

O arquivo é `CartorioGestao_3.6.15.cgu`, e a impressão digital SHA-256 dele é:

```
f4945acd8b02f4e07a4545448b69e34ea9e26d5837d9dd703c5d2cd639eafd82
```

O arquivo tem 1,1 MB. Para conferir no servidor, antes de aplicar:

```bat
certutil -hashfile CartorioGestao_3.6.15.cgu SHA256
```

### 4. Aplicar

```bat
ATUALIZAR_SISTEMA.cmd
```

### 5. Rodar a carga do acervo de novo

Em *Demais atribuições → Carga do acervo* — **só se você ainda não tiver aplicado
a 3.6.14**. Ela é repetível por construção: o que já está no banco volta como
"repetido" e não se duplica.

Ao terminar, a tela deve mostrar, nas contagens do Registro Civil:

- `pessoas_de_filiacao: 1084`
- `atos_de_registro: 244`
- `assentos_com_livro_a_confirmar: 3`

**Se algum número vier diferente disso, me diga antes de seguir.**

### 6. Responder o que só você sabe

Em *Demais atribuições → O que falta informar*. As pendências abertas hoje:

1. o próximo número do **Registro de Protestos** e do **Registro de Pagamentos**
2. a **letra da posição 566** do retorno da CRA, para apresentante novo — `A`,
   `P` ou branco
3. o **Livro 6 de Apontamento**, aberto em 05/03/2024 e nunca usado
4. o próximo número dos **três livros do RCPN** que o E-Ofício nunca teve —
   B-Auxiliar, C-Auxiliar e D
5. **os três casamentos do livro duvidoso** — já decidida por você: fica como
   está, e a confirmação acontece na ficha de cada um, quando forem consultados

E o passo seu para usar a ajuda, se ainda não fez: **informar a chave da API** em
*Administrativo → Ajuda — configurar*.

---

## Depois de aplicar, um passeio de dois minutos

1. Abra qualquer tela e olhe o canto de baixo, à direita: o botão **Ajuda desta
   tela** tem de estar lá.
2. Abra-o e pergunte alguma coisa que você já sabe responder — por exemplo,
   *"onde eu emito uma certidão de nascimento?"*. A resposta tem de citar a tela
   **pelo nome que está no seu menu**.
3. Vá a *Administrativo → Problemas do sistema* e clique em **Conferir a casa**.
   Numa casa em ordem ela diz que não achou nada; se achar, o que achou vira
   linha na lista.
4. Clique em **Gerar o relatório para conserto** e abra o arquivo que baixar. É
   ele que me mandar quando alguma coisa estiver errada.

---

## Se algo der errado

```bat
net stop CartorioGestao
copy "%PROGRAMDATA%\CartorioGestao\cartorio_gestao-antes-da-3.6.15.sqlite3" "%PROGRAMDATA%\CartorioGestao\cartorio_gestao.sqlite3"
```

e me diga o que apareceu na tela, com as palavras que estavam escritas nela.

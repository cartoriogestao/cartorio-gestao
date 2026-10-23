# O que temos e o que falta

Medido em **27/08/2026**, contra o servidor e contra o código — e não de
memória. A leitura anterior, de 26/08, ficou dentro deste mesmo arquivo: o que
mudou de um dia para o outro está dito onde mudou.

---

## A resposta curta

**A 3.6.15 foi aplicada no servidor em 27/08/2026, às 08h41.** A distância entre
o que estava pronto e o que estava rodando — que era o maior buraco deste
sistema — deixou de existir.

Conferido hoje, arquivo por arquivo: **os 232 arquivos de programa do projeto e
do servidor batem byte a byte.** O banco migrou sozinho ao subir, e o dado
antigo está inteiro.

> **O que falta agora é de outra natureza: rodar a carga do acervo.** As quatro
> atribuições novas estão de pé e **vazias**, e nenhum contador foi semeado.
> Enquanto isso não for feito, o primeiro ato novo de cada série nasceria com o
> número 1 sobre acervo que já passou disso.

---

## O que está RODANDO no servidor

Conferido comparando **arquivo por arquivo** o projeto com
`C:\Program Files\CartorioGestao`, e lendo o banco do servidor:

| | |
|---|---|
| Versão rodando | **3.6.15**, aplicada em 27/08/2026 às 08h41 |
| Como foi aplicada | `ATUALIZAR_SISTEMA.cmd` — a via rápida, que copia código e telas |
| Onde | `C:\Program Files\CartorioGestao` |
| Banco | `C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3` — **108 tabelas**, migrado |
| Uso | **suspenso desde 18/08/2026** — não há ato novo na auditoria |
| Backup de antes | `backup_completo_20260826_150121.zip`, de 26/08 às 15h01 |

O que há de dado vivo nele:

| Atribuição | Quanto |
|---|---|
| Caixa — lançamentos | 18.396 |
| Registro de Imóveis — matrículas | 1.701 |
| Registro de Imóveis — atos | 1.245 |
| Notas — atos | 259 |
| Usuários | 6 |

E o que **existe e está vazio**: as tabelas de Protesto, de Registro Civil, de
RCPJ/RTD, do Livro 3, do núcleo de livros, do razão de selos, da lista de
fraudes, da ajuda e dos problemas. Elas chegaram agora, com a 3.6.15, e o que
falta pôr dentro delas é o acervo — o passo 5 do roteiro.

> **Um carimbo que ficou para trás, e foi corrigido.** `install.json` e
> `VERSAO.txt` continuam dizendo **3.2.1**: o `ATUALIZAR_SISTEMA.cmd` copiava
> código e telas, e não o carimbo da versão. O sistema roda a 3.6.15 — a
> `VERSION` mora no `app.py`, e é ela que aparece no rodapé da tela e que o
> atualizador usa. Quem lesse os dois arquivos, porém, leria a versão errada;
> foi o que aconteceu na conferência de hoje. O script passou a carimbar, como
> o caminho do `.cgu` já fazia.

---

## O que está PRONTO e esperando

**Dezesseis pacotes** na pasta do projeto. O mais novo, a **3.6.15**
(SHA-256 `f4945acd…eafd82`, 1,1 MB), **já está aplicado no servidor desde
27/08**. Os outros ficam como registro do caminho.

O tamanho do que eles trazem:

| | |
|---|---|
| Módulos | 86 |
| Linhas de código | 47.918 |
| Telas | 125 |
| Rotas | 226 |
| Arquivos de teste | 68 |
| **Testes, todos passando** | **1.971** (mais 7 pulados, que dependem do selador) |

### As seis atribuições, construídas

| Atribuição | O que tem |
|---|---|
| **Notas** | já existia na 3.2.1 — livros, atos, etiquetas, assinaturas |
| **Registro de Imóveis** | já existia — matrículas, atos, CNIB, ONR, **mais o usucapião como processo** |
| **Protesto** | título, apontamento, intimação, protesto, pagamento, cancelamento, certidão, os **cinco arquivos da CRA**, aviso, entrega e edital |
| **RCPN** | assento, a divisão tripartite, e agora **a certidão no modelo do CNJ** |
| **RCPJ e RTD** | registro, atos, certidão de inteiro teor |
| **Registro Auxiliar (Livro 3)** | registro, atos, certidão |

### O que serve as seis

- **o núcleo dos livros** — 24 séries, geometria das folhas, numeração que não
  repete, inutilização, encerramento diário e os termos em `.odt`
- **o selo** — o contrato do selador (181 endpoints), o razão, o selo à mão
  com conferência, e a senha guardada fora do banco
- **as custas** — os quatro fundos, gratuidade, vigência pela data do ato, e a
  receita medida em 24.849 selos reais
- **a lista de atenção para fraudes** — ligada nas **sete portas** por onde
  entra pessoa nesta casa
- **a aba do que só você pode informar**, com aviso em qualquer tela
- **a carga do acervo** — 1.366 títulos, 244 assentos, 72 registros, 14 do
  Livro 3, e agora 1.084 pessoas de filiação
- **a ajuda do sistema**, numa janela em **qualquer** tela, com o mapa medido
  desta instalação; e a lista de problemas, que o sistema anota sozinho quando
  uma tela quebra, com o relatório para o conserto

---

## O que FALTA

### 1. Rodar a carga do acervo — e este é o item que importa

~~Aplicar o que está pronto~~ — **feito em 27/08/2026**. O que ficou do roteiro
é o passo 5: *Demais atribuições → Carga do acervo*.

Ela é repetível por construção, e é o que põe dentro do sistema os 1.366
títulos de Protesto, os 244 assentos do Registro Civil, os 72 registros de
RCPJ/RTD e os 14 do Livro 3 — e, no fim, **semeia os contadores**, que é o que
impede o defeito de 18/08 de acontecer outra vez.

Ao terminar, as contagens do Registro Civil têm de mostrar
`pessoas_de_filiacao: 1084`, `atos_de_registro: 244` e
`assentos_com_livro_a_confirmar: 3`. **Número diferente disso quer dizer que o
acervo do servidor não é o que foi medido** — pare e diga.

Depois dela, o passo 6: responder o que só você sabe.

**O backup de antes da atualização** é o `backup_completo_20260826_150121.zip`,
de 26/08 às 15h01 — o automático de hoje (08h46) já é posterior à migração.

### 2. A revisão ato por ato, que ainda não passou por duas atribuições

A fase 6 cobriu Protesto, RCPN, RCPJ/RTD e Livro 3. Faltam:

| O que | Tamanho | Por quê |
|---|---|---|
| **Notas** | grande | é onde a casa mais trabalha — metade do movimento é reconhecimento de firma |
| **Registro de Imóveis** | grande | e tem o usucapião já feito por dentro |

São as duas atribuições **mais antigas** do sistema — nasceram antes do núcleo,
e por isso são as que mais provavelmente têm o defeito que esta revisão acha
sempre: função pronta que nenhuma tela chama.

### 3. As remessas externas do Registro Civil

SIRC, CRC, IBGE e DNV. Cada uma é um layout a medir antes de escrever.
**Nenhuma trava o balcão** — são obrigações de envio, não de atendimento.

### 4. Três coisas que estão BLOQUEADAS, e não paradas por descuido

| O que | Por que não dá |
|---|---|
| **Dígito da matrícula** de 32 dígitos do RCPN | 243 amostras testadas contra módulo 11 (quatro famílias de pesos, duas convenções, dez mapeamentos), módulo 97 e Luhn — o melhor acertou 46. Nível de acaso |
| **Código de barras do boleto** do aviso de intimação | busca exaustiva das 9⁴ combinações de pesos: melhor acerto 465 de 1.618 |
| **Receita de custas do RCPN** | não há o que medir — o E-Ofício mandou o `codigoAto` **vazio** nos 1.238 atos do civil |

Nos três casos o sistema **guarda o que vier e não inventa**. Número chutado em
matrícula ou em código de barras não dá erro: dá dinheiro no lugar errado e
certidão recusada em outro estado.

### 5. O backlog antigo do balcão

Catorze itens pequenos, herdados da 3.2.1: prenotação não vinculada ao ato,
marca REURB-S não gravada, comprovante com prazo errado, `conferido_por` nunca
escrito, CNM nem gerado nem validado, cancelar certidão e encerrar protocolo
com rota mas sem botão, recibo DOI dizendo sucesso sem remessa, e mais.

---

## O que espera VOCÊ

Estão na aba *Demais atribuições → O que falta informar*, com aviso em qualquer
tela. Nenhuma trava o balcão hoje; as duas primeiras travam o **primeiro ato
novo** de cada série.

1. **O próximo número do Registro de Protestos e do de Pagamentos.** O acervo
   guarda o livro e a folha do protesto, e nenhuma coluna com o número. Sem
   isso, o primeiro ato novo nasce com o **número 1** sobre acervo que já passou
   de 2.000 — o defeito de 18/08 outra vez.
2. **O próximo número dos três livros do RCPN** que o E-Ofício nunca teve:
   B-Auxiliar, C-Auxiliar e D. *(Menos urgente depois da sua resposta de 26/08:
   não entra casamento religioso há anos.)*
3. **A letra da posição 566** do retorno da CRA, para apresentante novo. São
   três caminhos aceitos: `A`, `P` e **branco**.
4. **O Livro 6 de Apontamento**, aberto em 05/03/2024 e nunca usado.
5. **Os três casamentos do livro duvidoso** — já decidido: ficam como o
   E-Ofício guardou, e a confirmação acontece na ficha de cada um quando forem
   consultados.

---

## E uma coisa para lembrar quando tudo estiver rodando

**O certificado do selador está vencido desde 10/11/2025.** Não impede de
selar — o sistema fixa o certificado, e fixar é dizer "é esta máquina, eu
conferi". Mas você pediu para ser lembrado, para cobrar a renovação de quem
mantém o aparelho.

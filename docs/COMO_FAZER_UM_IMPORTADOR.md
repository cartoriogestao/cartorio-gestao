# Como fazer um importador de acervo

Para quem — pessoa ou IA — vai trazer para o Cartório Gestão o acervo de
**outro** sistema. A importação do E-Ofício terminou nesta serventia em
17/10/2026. Os botões dela saíram da tela, mas os importadores **ficaram** no
código, com os testes, como exemplo vivo. Este guia diz por onde começar e o
que eles ensinam.

Nada aqui traz nome, documento ou endereço de pessoa. Os números são
contagens medidas no acervo desta casa.

---

## 1. Primeiro, tente a importação padrão

O destino preferido é a **importação padrão**: `importar_padrao.py`, na tela
*Livros e acervo → Importar de outro sistema* (`/importar-padrao`,
`atribuicoes_web.importar_padrao_tela`).

**Como ela funciona**

- O outro sistema não precisa de código novo aqui: basta um **arquivo JSON**
  com os nomes das colunas do Cartório Gestão.
- O arquivo traz `formato="CARTORIO_GESTAO_IMPORTACAO"`, `versao`, `especie`,
  `de_onde_veio` e `registros[]`.
- Cada registro tem uma `chave`, que é o identificador dele no sistema de
  origem.
- Os campos aceitos são lidos do próprio esquema (`_colunas`). O arquivo
  **não** pode mandar `id`, `origem`, `origem_chave`, `criado_*` nem as
  colunas `*_norm` (`DA_MAQUINA`).
- O manual, com a lista de campos e um exemplo montado do banco, é baixado em
  `/importar-padrao/manual` (`importar_padrao.manual`). Esse é o arquivo para
  entregar ao técnico do outro sistema.

**O fluxo**

- `conferir()` só lê e devolve a prévia.
- `importar()` confere de novo e então grava.
- Registro recusado volta com o número da linha e o motivo.
- `chave` que já entrou vai para `repetidos` e não duplica.
- Tudo é gravado com `origem='IMPORTACAO'` e `origem_chave` = a chave.
- A importação traz acervo, mas **não lavra ato**: não toma número, não ocupa
  folha, não sela e não cobra.

### O que ela cobre hoje (`MODELOS`)

| Espécie | Tabela de destino | Observação |
|---|---|---|
| `RCPN_ASSENTO` | `rc_assentos` e `rc_pessoas` | as pessoas vão no campo `pessoas` |
| `RI_MATRICULA` | `ri_matriculas` | só a matrícula |
| `RCPJ_RTD_REGISTRO` | `rg_registros` | só o registro |
| `LIVRO3_REGISTRO` | `ra_registros` | só o registro |
| `NOTAS_ATO` | `nt_atos` | sem as partes |
| `PROTESTO_TITULO` | `pt_titulos` | sem devedores e sem os atos do título |

### O que ela NÃO cobre — e o E-Ofício trazia

| Coisa | Quem trazia do E-Ofício |
|---|---|
| Atos, partes, protocolos e certidões do RI | `ri_import.Importador.executar` |
| Imagens das fichas do RI | `ri_import`, mais `ri_web.ri_resolver_imagens` e `ri_copiar_imagens` |
| Ordens do CNIB | `ri_import` |
| Par (credencial) do CNIB | `cnib_web.cnib_credencial_do_acervo` |
| Partes e averbações do Livro 3 | `acervo_carga` (rota `livro3_importar_acervo`) |
| Devedores e atos do protesto | `acervo_carga.carregar_tudo` (protesto) |
| Apresentantes do protesto (CNPJ e tipo) | `protesto_cenprot_xml.carregar_apresentantes` |
| Cartões de autógrafo e as imagens das firmas | `notas_import` (cartões e imagens) e `notas_web.notas_assinaturas` |
| Modelos de notas; claros `@` dos modelos do RCPN | `notas_import` (modelos); `rc_modelos_livres.traduzir_do_eoficio` |
| Caixa e protocolo (custas, lançamentos) | `caixa_import.importar` |
| Tabela de emolumentos | `emolumentos.importar` |
| Configuração do selador | `selador_config.importar_do_eoficio` |
| Selos já emitidos; papel de segurança | `acervo_carga` (selos, papel) |
| Contadores dos livros (próximo número) | `acervo_carga.semear_numeracao`, `ri_import.fixar_numeracao` |

Se o acervo novo tem alguma coisa da segunda tabela, há dois caminhos:

1. **Acrescentar uma espécie em `MODELOS`.** É o melhor caminho, porque o
   próximo sistema também ganha.
2. **Escrever um importador próprio**, seguindo as regras abaixo.

---

## 2. Os importadores do E-Ofício, como exemplo

| Módulo | O que traz |
|---|---|
| `acervo_eoficio.carregar` | Copia as tabelas do E-Ofício **cruas**, sem interpretar, para `acervo_eoficio.sqlite3`. Confere a cópia pelo manifesto. |
| `acervo_eo_vivo.atualizar_protesto_ao_vivo` | Puxa do banco vivo (MSSQL) as tabelas de protesto que o snapshot não tinha. Também não interpreta. |
| `acervo_carga.carregar_tudo` | Protesto, RCPN, RCPJ/RTD, Livro 3, papel de segurança, IBGE e selos. Depois semeia a numeração dos livros. |
| `ri_import.Importador.executar` | Registro de Imóveis: matrículas, atos, partes, imagens, protocolos, CNIB e certidões. |
| `notas_import.importar` | Notas: domínios, cartões, imagens, reconhecimentos, autenticações, livros, modelos, procurações e escrituras. |
| `caixa_import.importar` | Protocolos, itens de custas, caixas e lançamentos. |
| `emolumentos.importar` | A tabela de emolumentos, por vigência. |
| `selador_config.importar_do_eoficio` | Endereço, usuário e senha do selador. A senha fica fora do banco. |

As rotas continuam vivas pelo endereço, para o administrador:

- `/atribuicoes/importar`
- `/notas/importar`
- `/caixa/importar`
- `/registro-imoveis/importar`
- `/protesto/importar-eoficio`
- `/rcpn/importar-acervo`
- `/livro3/importar-do-acervo`
- `/notas/assinaturas`

O guarda disso é `tests/test_sem_botao_do_eoficio.py`.

---

## 3. O que eles ensinam

### Separe a cópia da interpretação

`acervo_eoficio` só copia, e `acervo_carga` só interpreta. Assim, quando a
interpretação erra, ela se refaz sem voltar ao sistema antigo — que um dia
estará desligado.

### Ordem da carga: quem é apontado entra antes

A ordem de `acervo_carga.CARGAS` é:

1. protesto
2. RCPN
3. RCPJ/RTD
4. Livro 3
5. papel de segurança
6. IBGE
7. selos

Os selos ficam por último porque se amarram aos atos. Dentro de cada carga
vale a mesma regra: o assento entra antes da filiação e do ato de registro, e
o título antes dos devedores. Em `notas_import`, os cartões entram antes das
imagens e dos reconhecimentos.

No PostgreSQL a chave estrangeira é cobrada: carga fora de ordem não «dá
certo depois», ela estoura.

### Acervo não se renumera, não se sela, não se cobra

O ato antigo entra com o número, o livro e a folha que já tem no papel.

- `acervo_carga` não ocupa lugar em livro pelo núcleo.
- Do selo, só copia o número que veio no acervo.
- Nada passa pelo caixa.

O que o importador **semeia** é o contador do livro, para o próximo ato novo
não nascer com o número 1 (`semear_numeracao`). O contador **nunca desce**.
Quando o sistema antigo não informa o contador, ou ele discorda do maior
número carregado, a carga **declara uma pendência** em `nu_implantacao`
(`implantacao.declarar_numeracao`). A tela *O que falta informar* mostra a
pendência para o oficial responder, em vez de o importador chutar.

### Nada é descartado em silêncio

Linha que não entra vai para a **quarentena**, com o motivo:

- `ri_rejeitados`
- `nt_rejeitados`
- `cx_rejeitados`

Em `acervo_carga`, a classe `Carga` separa três coisas:

- **rejeitar**: não entrou, e diz por quê;
- **avisar**: entrou, mas confira;
- **contar**: o resultado da carga.

A tela da importação mostra a quarentena. «Entraram 1.701» sem dizer quantas
ficaram de fora é meia resposta.

### Duplicadas

- Cada linha leva `origem` e `origem_chave` (por exemplo
  `tabela:chave-no-sistema-antigo`).
- A tabela tem `UNIQUE(origem, origem_chave)`.
- A gravação é `ON CONFLICT DO NOTHING`.

Com isso, rodar a carga duas vezes não duplica nada, e a segunda passada só
completa o que faltou. A exceção é o RI (`ri_import`): duas matrículas com o
mesmo número, livro e complemento ficam como **uma**, a mais completa, e as
outras vão para a quarentena com a chave da que ficou. Uma segunda carga do RI
exige marcar «substituir», que apaga só o que tem `origem='EOFICIO'`.

### Campo que existe não quer dizer campo que foi usado

`bitFinalizado`, do caixa do E-Ofício, é falso nas 21.342 linhas. O campo
existia, mas a casa nunca o usou. Por isso `caixa_import` deduz a situação
(aberto, a pagar ou pago) das custas e do caixa, em vez de confiar no campo
(`caixa_import.py`, no início do módulo; `templates/caixa_importar.html`).

Antes de mapear uma coluna, **meça**: quantos valores distintos, quantos
nulos, e se o valor acompanha o que deveria acompanhar.

### A quantidade que não multiplicava

`tools/quantidade_nas_custas_do_eoficio.py` mediu o problema:

- O E-Ofício gravava nas custas o valor **unitário**, com a quantidade ao
  lado. Quem multiplicava era a tela dele.
- A carga copiou a coluna como se fosse o total.
- Eram 7.483 dos 32.393 itens com quantidade maior que 1, e
  R$ 643.694,38 deixavam de ser somados.

A prova foi feita no acervo: em 185 pares (código do TJ, ano) o valor é
constante qualquer que seja a quantidade, e em nenhum ele escala.
`caixa_import` hoje multiplica. O script corrige o que já tinha entrado, só
com `--confirmar`, e recusa item já quitado.

A lição: o **significado** de uma coluna é medido nos dados, não deduzido do
nome.

### A coluna de proveniência serve depois da carga

A tela *Corrigir dado do acervo* (`acervo_correcao.py`) só deixa corrigir o
que veio do acervo. Ela reconhece o acervo pela coluna `origem`
(`valores_acervo=("EOFICIO",)` em `TABELAS`), nas tabelas `ri_matriculas`,
`rc_assentos`, `rc_pessoas`, `rg_registros`, `nt_atos` e `nt_cartoes`.

Por isso:

- Grave **sempre** `origem` e `origem_chave`.
- O que entrar por `IMPORTACAO`, ou por uma origem nova, **ainda não** é
  corrigível por essa tela. Para que seja, acrescente o valor em
  `valores_acervo`, com teste.

### Importador sem tela é importador que ninguém roda

O defeito que mais se repetiu neste projeto foi a função pronta, testada, que
ninguém consegue alcançar:

- `importar_padrao.py`, no início do módulo, sobre `ri_import` e
  `notas_import`;
- `tests/test_funcao_sem_tela.py`.

O mesmo vale para rodar por script: o banco fica na pasta de dados e o
serviço é quem o abre. Por fora, exige administrador, e foi aí que uma
tentativa se perdeu (`ri_web.ri_importacoes`, ação `tipo_imovel`).

Importador novo nasce com:

- tela;
- prévia que só lê;
- botão que grava;
- quarentena visível;
- auditoria (`audit(...)`).

Quando a importação acabar, tire o botão e deixe a rota, como foi feito aqui.

### Leia só o que foi exportado

Os importadores leem a exportação (`.jsonl`, `.sqlite3`). O próprio sistema
antigo só é lido, e só quando inevitável (`acervo_eo_vivo`). Nunca se escreve
nele.

---

## 4. Lista curta para o importador novo

1. A importação padrão serve? Se faltar uma espécie, acrescente-a em
   `MODELOS`.
2. Copie cru primeiro e interprete depois, em passos separados.
3. Ponha a carga na ordem das chaves estrangeiras.
4. Grave `origem` e `origem_chave`, com `UNIQUE` e `ON CONFLICT DO NOTHING`.
5. Mande os rejeitados para a quarentena com motivo, e mostre-os na tela.
6. Não renumere, não sele, não cobre. Semeie o contador e declare a
   pendência quando não souber.
7. Meça cada coluna antes de confiar nela: campo sem uso, valor unitário
   contra total.
8. Tela com prévia, botão que grava e auditoria. Teste que prova que rodar
   duas vezes não duplica.
9. Ensine `acervo_correcao.TABELAS` a reconhecer a origem nova.

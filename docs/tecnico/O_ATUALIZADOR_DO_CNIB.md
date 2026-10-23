# O ATUALIZADOR DO CNIB — 19/09/2026

    «verifique o estado do atualizador da cnib do sistema»
    «o atualizador consegue puxar a base diaria automaticamente?»
    «vamos fazer tudo e arrumar tudo e baixar tudo»
                                        — o oficial, 19/09/2026

---

## 1. O ESTADO QUE A PERGUNTA DELE ENCONTROU

**O transporte estava pronto e não havia ninguém do outro lado.** Medido em
19/09/2026, antes de escrever uma linha:

| | |
|---|---|
| `cnib_api.py` | 813 linhas, de 18/09/2026, **no servidor** (byte a byte igual à árvore) |
| testes dele | **35 passam em 4,8 s**, contra brutos transcritos da Central |
| quem o importa fora de teste | **ninguém** |
| quem grava em `ri_cnib_ordens` | só `ri_import` (a carga do E-Ofício), `origem='EOFICIO'` |
| `cnib.cred` no `%PROGRAMDATA%` | **não existe** — `centrais_cred.tem(CNIB, PRODUCAO)` é `False` |
| o espelho | **50.054** ordens · 37.694 ativas · ordem mais recente **19/03/2023** |
| atraso | **1.280 dias** — 3 anos e 6 meses |
| `ri_cnib_decisoes` | vazia |

E o próprio projeto já declarava isso: `tests/test_funcao_sem_tela.py`, bloco
`ACHADAS_EM_19_09_2026`, com doze funções do `cnib_api` marcadas *«pronta e
testada, ainda sem rota/tela»*. **A peça viajou no `.cgu`, chegou ao servidor e
não tinha porta.**

---

## 2. NÃO EXISTE «BASE DIÁRIA» PARA BAIXAR

O contrato (`FONTES_EXTERNAS/onr_serventias/swagger_v1.json`) tem **7 caminhos,
todos POST**, e **nenhum entrega arquivo ou base**. Não há o equivalente ao
`.mrc` do SIRC nem à carga da CRC. «Puxar a base» no CNIB quer dizer **varrer
páginas** de `/api/v2/ordem/visualizar` numa janela de datas.

**Automaticamente, sim** — e na forma que esta casa já tem rodando:
`automatic_backup_once` (`app.py`), disparado no `before_request`, com trava de
processo, chave de desligar, «só o que ainda não foi feito hoje» e falha que
não derruba a tela.

**Com uma diferença que mudou o desenho:** o backup é trabalho de disco; esta
rotina sai para a **rede**, com prazo de 60 s por página. Prendê-la no
`before_request` faria a primeira tela do dia ficar girando. Ela vai numa
**linha de fundo** (`threading.Thread(daemon=True)`), como a descoberta de rede
— e cada linha dessas abre a **sua própria** conexão, que é como o `Database`
desta casa funciona (`connect()` devolve conexão nova a cada chamada).

**O limite honesto, e ele está escrito na tela:** a rotina roda quando alguém
abre o sistema. Dia em que ninguém abrir é dia sem leitura — e é por isso que a
janela **volta sete dias atrás**.

---

## 3. AS SETE MEDIÇÕES QUE GOVERNAM O MÓDULO

Estão no cabeçalho de `cnib_atualizador.py`, e cada uma custou uma ida à rede
em 18/09/2026:

1. **`ordens_visualizadas=True` SEMPRE — e aqui é segurança.** Com `False` a
   leitura **consome a fila**: 341.697 ordens ficaram 341.497 depois de uma
   página de 200. Um trabalho que roda sozinho, todo dia, com `False`,
   esvaziaria a fila desta serventia sem ninguém ver. **O módulo não tem
   parâmetro para mudar isso:** o que não se pode escolher errado não se
   oferece.
2. **As páginas não são disjuntas** — 2.996 distintas em 3.000. Gravação por
   UPSERT em `protocolo_cnib`, cujo índice único já existia.
3. **O zero da Central não é prova de ausência** — a mesma resposta vazia veio
   para dias que tinham ordens. Janela sobreposta, e nunca apagar o que não
   veio.
4. **`forma_estranha` não é `vazio`.** Os dois devolvem zero ordens. A forma
   estranha vira **recusa escrita** (`RECUSADA`) e **a janela não anda**.
5. **Cancelamento não se desfaz por linha que não fala dele.** A mesma janela
   traz a ordem e o cancelamento dela; se a ordem chegar depois, um `DO UPDATE`
   ingênuo a reativaria. O `COALESCE` nos dois campos e o `CASE` do `ativa`
   fecham isso — **foi o primeiro defeito que este módulo teve de não ter**.
6. **A rede não entra na transação.** `ler_da_central` não recebe `con`;
   `gravar` não vai à rede. São duas funções por causa disso.
7. **A data da cópia não é `MAX(data_pedido)`.** A janela filtra pela data da
   **atividade**: uma janela de junho/2026 devolveu ordem com `datapedido` de
   2012, porque o que se moveu foi o cancelamento. Quem responde «até quando
   esta cópia vale» é `ri_cnib_leituras`.

---

## 4. O DEFEITO QUE A PRIMEIRA LEITURA TERIA CRIADO

**A posta em dia encolheria sozinha.** A lista dos pedaços começava no
`MAX(data_pedido)` da tabela; bastaria a Central mandar **uma** ordem pedida
hoje para o máximo pular para hoje — e os 43 meses de atraso virariam um mês,
**com a tela dizendo que está tudo em dia**.

O começo passou a ser o **retrato do acervo**
(`MAX(data_pedido) WHERE origem <> 'CNIB'`), que não se move: aquelas 50.054
linhas pararam em 19/03/2023 e param ali para sempre. Há teste que grava uma
ordem de hoje pela Central e exige que a lista **não encolha**.

---

## 5. A POSTA EM DIA NÃO CABE NA ROTINA

A fila tinha **341.697 ordens**. A 500 por página são **684 páginas**, acima do
freio de 200 (100.000) do `cnib_api` — que existe para o servidor da serventia
não varrer o país num pedido.

Por isso ela anda **mês a mês**: de **março de 2023** a **setembro de 2026**,
**43 pedaços**, cada um com o seu botão e a sua linha anotada. O mês é o pedaço
que a tela consegue nomear e que o oficial reconhece; se algum estourar o teto,
a leitura fica marcada `parou_no_teto` e **aparece na tela**.

**A rotina diária não faz a posta em dia**, e isso está escrito na tela: o
tamanho do que se pede à Central é decisão de gente.

---

## 6. O QUE FOI CONSTRUÍDO

| | |
|---|---|
| `cnib_atualizador.py` | o domínio — janela, gravação, leituras anotadas |
| `ri_cnib_leituras` (em `ri_schema`) | cada ida à Central, **inclusive as que deram errado** |
| `cnib_web.py` | a tela, a ida, o CPF, o interruptor e a rotina diária |
| `templates/cnib_central.html` | «CNIB — a cópia local e a Central» |
| `tests/test_cnib_atualizador.py` | 16 testes |

**As leituras que deram errado ficam na lista de propósito:** «não há ordem
nova» e «faz uma semana que não se fala com a Central» são coisas diferentes, e
a segunda é a que precisa de gente.

---

## 7. OS DOIS CONSERTOS DE PASSAGEM

**1. O token velho sobrevivia à troca da credencial.** Em
`configuracoes_central` (`app.py`) só o ONR chamava `esquecer_o_token`. O CNIB
cai na mesma armadilha — token de uma hora guardado na memória do processo —, e
**o módulo já trazia a função pronta; faltava chamá-la**. Hoje é inofensivo
porque nada pede token; viraria real no dia em que o atualizador rodasse.

**2. A ficha do imóvel envelheceria a cada leitura.** `cnib_referencia`
(`ri_web.py`) respondia «até quando esta cópia vale» com `MAX(data_pedido)` — e
uma leitura de hoje que trouxesse o cancelamento de uma ordem de 2012 **baixaria**
a data mostrada. Agora ela pergunta à última leitura boa, e cai no
`MAX(data_pedido)` só enquanto não houver leitura nenhuma.

---

## 8. O QUE FALTA, E É CLIQUE DELE

**A credencial.** O par está no acervo — `tbCNIB_Propriedades`, uma linha,
`Cliente_ID = cns-000000` e um `Secret_Code` de 44 caracteres —, e **não em
papel nenhum**. Sem o botão, informá-lo quer dizer abrir um arquivo de 382 MB
com ferramenta de programador e copiar uma senha à mão, que é exatamente a
operação em que uma senha vaza para um bloco de notas.

Por isso a tela tem **«Trazer o par do CNIB do acervo do E-Ofício»**: o segredo
é lido e gravado no `%PROGRAMDATA%` **no mesmo passo, dentro do servidor**; o
navegador recebe só a frase de que deu certo, e a auditoria registra **que** se
trouxe, nunca o quê. É só do ADMIN, como a própria tela de credenciais.

**E o CPF de quem consulta**, que a Central exige em todo pedido — ele não é
segredo e fica em `settings`, ao lado do interruptor da rotina.

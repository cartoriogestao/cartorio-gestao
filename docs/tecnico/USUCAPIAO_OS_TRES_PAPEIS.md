# O usucapião: os três papéis do rito

**Relatos #30 e #21 do oficial, 30/08/2026:**

> «o módulo de processo de usucapião precisa ter campo para subir as informações
> necessárias aos atos que o cartório precisará praticar, como as notificações,
> e gerar modelo e manual de como efetuar»

> «o cadastramento é muito simples e não parece ser maduro para processar um
> usucapião no RI com confiança»

---

## O rito tem três atos que produzem papel

E até 30/08/2026 **nenhum dos três tinha modelo**. Eram etapas com nome e sem
papel: quem chegasse nelas escrevia o documento à mão, e dois editais sairiam
diferentes.

| etapa | o papel | a base |
|---|---|---|
| `NOTIFICACAO` | notificação de titulares e confrontantes | LRP art. 216-A, § 2º; Código TJMA art. 754 |
| `CIENCIA_ENTES` | ofício à União, ao Estado e ao Município | LRP art. 216-A, § 3º |
| `EDITAL` | edital para terceiros interessados | LRP art. 216-A, § 4º; Código TJMA art. 755 |

---

## O que faltava na notificação

Ela **já existia como movimento** — destinatário, papel, prazo e resposta. O que
não existia era tudo o que faz dela **um ato praticado**:

| faltava | por que importa |
|---|---|
| **o endereço** | a norma dá três lugares possíveis e o sistema não guardava nenhum |
| **a forma e a tentativa** | são quatro formas **em ordem**, e o edital só cabe «caso frustradas as anteriores» — sem registrar a tentativa, ninguém prova que houve |
| **o papel** | não havia modelo |
| **o prazo** | o rito tem prazo e o sistema não sabia nenhum |

**A regra não foi inventada: foi importada.** O art. 754 manda aplicar, na
notificação de confrontante, «no que couber, o procedimento de retificação de
registro» — e este sistema já leu esses artigos. As formas e os endereços **são
os mesmos objetos** de `rt_tjma`, não uma cópia. Há teste que garante.

---

## A procedência de cada prazo fica à vista

**«Lido» é o que se conferiu no PDF do Código de Normas, que está nesta casa.
«Citado» vem da Lei de Registros Públicos, cujo texto oficial não foi lido aqui
dentro.**

A diferença importa porque **prazo errado numa notificação não aparece como
erro**: aparece como impugnação perdida meses depois. Onde a procedência é
«citado», o sistema mostra o prazo e **não o impõe** — quem confirma é quem
responde pela serventia, com a lei aberta.

E o mais perigoso de errar é o do titular tabular: **o silêncio é concordância**,
e o prazo errado para menos produz anuência de quem ainda podia impugnar.

---

## O edital, e os dois saltos

**O prazo não conta da disponibilização.** São dois «primeiro dia útil seguinte»
encadeados (art. 755, § 1º): um para achar a data da publicação, outro para
começar a contar. Quem lê com pressa conta de um só — e **num edital, errar por
um dia é recomeçar o edital**.

Quem calcula é `us_tjma.inicio_do_prazo`, que sabe dos feriados desta comarca. O
papel remete ao artigo em vez de afirmar uma data que o montador não tem como
saber.

**Sem origem registrária, o edital tem de consignar isso expressamente** (art.
755, § 2º) — e a tela pergunta. Um edital que cala sobre isso é edital que se
refaz.

**A data da disponibilização é de quem publica**, e não «hoje»: quem publica na
Central recebe dela a data, e é dessa data que saem os dois saltos.

---

## Os entes são três, e saem os três

**Avisar dois e esquecer o terceiro** é vício que só aparece quando o que faltou
reclamar — depois de o registro estar feito. Por isso o botão monta os três
ofícios de uma vez: deixar escolher qual abriria essa porta.

O prazo deles pode dobrar, **mediante solicitação justificada dentro do prazo
original** — não é automática, e não é de ofício.

---

## O que os três têm em comum

**O teor congela.** O papel que se entregou é o de então; remontá-lo depois
traria o processo como ele está hoje. É a mesma regra do termo do Registro Civil
e da certidão de protesto.

**O recibo vai no mesmo papel** da notificação. O que prova a notificação é o
comprovante que volta assinado, e não a linha no sistema — recibo em folha
separada é o que se perde.

**Nada é gravado se o papel não puder sair.** Se faltar endereço, ou a forma não
for uma das quatro da norma, nenhum movimento existe: movimento de notificação
sem papel que o sustente é uma linha dizendo que a serventia notificou alguém sem
ter notificado.

---

## E a IA saiu

Decisão do oficial no mesmo dia: *«tirar as referências à análise de IA, tratar
apenas como forma de exportação e importação de relatório para qualificação»*.

O que sai é um **relatório do processo**; o que volta é um **parecer**. Quem lê
não importa ao módulo — advogado, assessoria, outra serventia ou ferramenta.

**A proteção continua inteira, só mudou de nome**: o parecer entra *por
conferir*, e `decidir()` recusa fechar o processo apoiado em parecer que ninguém
leu. Isso valia quando se chamava IA e vale igual para um parecer de advogado —
**quem decide é o delegatário**.

**A chave gravada no banco ficou** (`ANALISE_IA` em `us_movimentos.tipo`):
trocá-la faria os movimentos já lançados apontarem para um tipo que não existe
mais, e eles sumiriam da tela sem ninguém ver. Renomeia-se a etiqueta; a chave
fica declarada como legado.

---

## O que ainda não está feito

**A publicação na Central não é automática.** O sistema monta o edital; publicar
e trazer o protocolo é passo de quem opera — como no e-Proclamas do Registro
Civil, e pelo mesmo motivo: a integração não existe ainda, e o que se pode fazer
com verdade hoje é o papel pronto e o protocolo anotado.

# Corrigir um título do protocolo — v3.3.6

**17/08/2026.** Construído e testado fora do ar. Nada vale enquanto o `ATUALIZAR_SISTEMA.cmd`
não rodar.

Motivado pelo **título 11548**, encerrado por engano.

---

## O que faltava

O protocolo do Registro de Imóveis só tinha **lista**. Dava para prenotar e dava para encerrar —
e mais nada. Encerrado por engano, não havia como voltar atrás. Digitado errado, não havia como
corrigir.

Agora o número do protocolo é clicável e abre a tela do título, com três coisas: **reabrir**,
**corrigir os dados** e **lançar depósito prévio**.

---

## Reabrir — e por que não bastava abrir outro protocolo

O número de ordem do protocolo é o que garante a **prioridade do direito** (Lei 6.015/73, art.
186). Abrir um protocolo novo joga o título para o fim da fila — e na frente dele pode ter
entrado outro título sobre o mesmo imóvel. Encerrado por engano, o que se precisa é desfazer o
engano, não recomeçar.

**A reabertura exige motivo** de pelo menos dez letras. Não é burocracia: reabertura de
prenotação é correção de ato de livro, e o motivo é o que se mostra na correição.

**Reabrir não apaga o encerramento.** Grava qual era a situação, quem reabriu, quando e por quê —
e isso passa a aparecer em destaque na tela do título, não escondido num log.

**O prazo NÃO é reiniciado.** É o ponto mais delicado da tela. A prenotação vale 20 dias úteis
contados do lançamento no protocolo, não do dia em que alguém corrigiu um erro de digitação.
Reabrir devolvendo prazo novo seria usar a correção para esticar a prioridade do título sobre
terceiros — e disso o sistema não participa. A tela diz isso ao reabrir, com a data em que a
prenotação vence.

---

## Corrigir os dados

Apresentante, CPF/CNPJ, natureza do título, objeto, matrícula, contato, documento apresentado e
anotação.

**A auditoria guarda o antes e o depois**, campo a campo — não um "protocolo 11548 editado", que
não responde à pergunta que a correição faz, que é *o que estava escrito antes*.

**Número de ordem, livro e data da prenotação não se corrigem por aqui.** São exatamente o que dá
prioridade ao título; mexer neles não é correção de cadastro.

Mudando o número da matrícula, o vínculo interno é reamarrado. Sem isso o protocolo mostraria uma
matrícula no texto e continuaria ligado a outra por dentro — pior do que não estar ligado a
nenhuma, porque parece certo.

---

## Depósito prévio no título

Botão na própria tela do título. É ali que o apresentante deixa o adiantamento; obrigar a sair,
abrir o caixa e procurar o protocolo é um passo que se esquece — e depois ninguém sabe a que
título o dinheiro pertencia.

- O depósito fica **amarrado ao título**, e o saldo somado aparece na tela.
- **Entra no caixa do dia** do operador. Depósito que não entra no caixa é a conferência que não
  fecha no fim do expediente, com ninguém lembrando do depósito da manhã.
- **Não havendo caixa aberto, o depósito é gravado assim mesmo** e a tela avisa em destaque. O
  dinheiro entrou; recusar o registro porque a gaveta está fechada seria perder o fato — e é
  assim que um depósito some.

### Uma decisão de estrutura

A criação do depósito passou a viver em **`caixa_depositos.py`**, e as duas telas — caixa e
Registro de Imóveis — chamam a mesma função.

A alternativa era copiar as trinta linhas para o `ri_web`. Não copiei: é a mesma armadilha que
produziu o defeito da função do usuário desta semana, onde a mesma regra vivia escrita em três
arquivos e um deles divergiu em silêncio. Há um teste que falha se alguém voltar a montar o
`INSERT` por fora do módulo.

---

## Como resolver o 11548

1. **`SERVIDOR\ATUALIZAR_SISTEMA.cmd`** — pede Administrador.
2. Menu → **Protocolo / prenotação** → clique no número **11548**.
3. **Desfazer o encerramento** → escreva o motivo (ex.: *encerrado por engano em 17/08; o título
   não chegou a ser registrado*) → **Reabrir o protocolo**.
4. Confira o prazo que a tela mostra. Se a prenotação já venceu no meio tempo, reabrir não
   ressuscita o prazo — e aí a decisão é jurídica, não de sistema.
5. **Depósito prévio** → valor, forma de pagamento → **Registrar depósito**.

Abra o caixa antes do passo 5, para o depósito entrar no movimento do dia.

---

## Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `caixa_depositos.py` | **novo** — a criação do depósito, numa implementação só |
| `templates/ri_protocolo_ver.html` | **nova** — a tela do título |
| `ri_web.py` | rota do título: reabrir, corrigir, depósito |
| `caixa_web.py` | passou a usar o módulo comum em vez da própria cópia |
| `ri_schema.py` | colunas da reabertura (`reaberto_em`, `_por`, `motivo`, `situacao_anterior`) |
| `caixa_schema.py` | `cx_depositos.ri_protocolo_id` |
| `templates/ri_protocolo.html` | o número do protocolo virou link |
| `tests/test_protocolo_reabrir.py` | **novo** — 23 testes |
| `app.py`, `VERSAO.txt` | 3.3.5 → 3.3.6 |

---

## Conferência

- **281 testes passando** (191 que já existiam, mais 90 das rodadas desta semana)
- Testado com o cenário real: protocolo **11548**, livro 1A, encerrado, prenotado há 5 dias
- Cobre: a tela abrindo, reabertura exigindo motivo, situação anterior gravada, reabertura
  visível na tela, **prazo não reiniciado**, auditoria com de/para, reabrir o que já está aberto,
  correção com antes/depois na auditoria, número de ordem protegido, matrícula reamarrada,
  depósito amarrado ao título, saldo somado, valor zero recusado, sem caixa aberto gravando e
  avisando, com caixa aberto entrando no movimento — e o teste que impede a regra do depósito de
  voltar a ser duplicada

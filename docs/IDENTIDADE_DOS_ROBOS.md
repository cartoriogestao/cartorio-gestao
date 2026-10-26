# Todo robô diz quem é e a mando de quem age

Ordem do oficial, 26/10/2026: «obrigação de todo robô se identificar e dizer a
mando de quem está agindo».

## A regra

1. **Robô entra com conta própria de robô.** Em Administrativo → Usuários, o
   ADMIN cria a conta com a marca «Conta de robô» (`users.eh_robo = 1`) e
   escolhe a **pessoa responsável** por ela (`users.robo_responsavel_id`: uma
   pessoa com cadastro ativo, nunca outro robô). Conta de robô só tem perfil
   USER ou AUDITOR.
2. **Robô com a senha de uma pessoa é proibido.** Isto não se impede por
   programa — nenhum programa distingue a mão da pessoa da mão do robô que tem
   a senha dela. É regra escrita, e quem a descumpre responde por ela.
3. **Quem grava sem usuário diz quem é.** Rotina, agente e script que gravam
   na auditoria fora de uma tela com login passam `agente=` (o próprio nome) e
   `a_mando_de=` (a pessoa que responde pela ordem). Para rotina agendada, a
   ordem é do **responsável pelas rotinas automáticas** — configuração em
   Usuários; vazia, vale o primeiro ADMIN ativo que não é robô.
4. **Não se procura robô no texto.** Nada no sistema lê a auditoria atrás de
   «bot», nome de IA ou cadência. A identidade é a declarada: a conta ou o
   `agente=`.

## Como gravar

```python
import identidade_do_robo as IDR

# fora da transação (rotina com o Database)
db.log(None, "SISTEMA", "MINHA_ACAO", "ENTIDADE", None, detalhes,
       agente="nome da rotina", a_mando_de=IDR.PELO_RESPONSAVEL)

# dentro da transação de quem chama
IDR.registrar(con, ts=agora, user_id=None, username="nome da rotina",
              action="MINHA_ACAO", entity_type="ENTIDADE", entity_id=None,
              details=detalhes, agente="nome da rotina",
              a_mando_de=IDR.PELO_RESPONSAVEL)
```

Ninguém escreve `INSERT INTO audit_logs` à mão: `tests/test_identidade_do_robo.py`
varre o repositório e recusa.

## As duas etapas

- **Etapa 1 (esta):** a linha sem usuário e sem identificação **grava** e é
  contada. A conferência do gestor («Robôs e rotinas que não dizem quem são»)
  vira tarefa da Gestão, e a tela Usuários mostra o quadro por origem.
- **Etapa 2 (depois, noutro PR, quando o aviso zerar):** a mesma linha é
  **recusada**. A troca é uma linha só: `identidade_do_robo.MODO = MODO_RECUSAR`.
  Quem decide «avisar ou recusar» é só `identidade_do_robo.decidir`.

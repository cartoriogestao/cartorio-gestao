# Fixtures do anti-vazamento

- `documentos_ficticios.txt` — allowlist de CPF/CNPJ/CNS **fictícios** (DV válido, bases zeradas).
- `limpo.txt` — texto sem nada sensível (deve passar).
- `com_cpf_ficticio.txt` — só documentos da allowlist (deve passar).

O caso "CPF válido NÃO permitido" **não** fica em arquivo: o teste gera o número
em tempo de execução (`tmp_path`), para nunca gravar no repositório um CPF com
DV válido que possa pertencer a alguém.

Esta pasta é ignorada pela varredura da árvore (`CAMINHOS_IGNORADOS`).

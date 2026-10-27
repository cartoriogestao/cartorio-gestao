"""A corrente de hash da auditoria — o lado Python. Só calcula.

Revisão de segurança da 3.7.0 (22/10/2026): `audit_logs` era uma tabela
comum — quem tivesse o banco apagava a linha de um ato e nada acusava. Desde
esta data cada linha leva `hash_anterior` (o `hash_linha` da última linha
encadeada) e `hash_linha` (SHA-256 dos campos dela mais o anterior). Quem
escreve o hash é o GATILHO `cg_auditoria_encadear` do PostgreSQL
(`banco_pg_funcoes.sql`), porque trinta e um arquivos inserem na tabela por
fora de `db.log`; este módulo recalcula, para a conferência da casa
(`compliance.regra_cadeia_da_auditoria`) acusar o que foi mexido.

OS DOIS LADOS TÊM DE BATER BYTE A BYTE: `CAMPOS` nesta ordem, `|` entre eles,
vazio onde é NULL, e o anterior por último. Quem mudar um lado muda o outro —
há teste que grava pelo banco e recalcula aqui.
"""
from __future__ import annotations

import hashlib
from typing import Any

#: as colunas de `audit_logs` que entram no hash, na ordem do gatilho
CAMPOS = ("ts", "user_id", "username_snapshot", "action", "entity_type",
          "entity_id", "details", "ip_address")

#: A VERSÃO 2 DA FÓRMULA (revisão de segurança de 26/10/2026): depois do
#: anterior entram `agente` e `a_mando_de` — quem agiu por programa e a mando
#: de quem. A versão vem da própria linha (`hash_versao`, escrita pelo
#: gatilho); sem ela (NULL, as linhas de antes da migração) vale a fórmula de
#: 22/10. Quem ler a linha para conferir tem de trazer as três colunas
#: (`SELECT *` basta).
CAMPOS_DA_VERSAO_2 = ("agente", "a_mando_de")


def versao_da_linha(linha: dict) -> int:
    """1 (a fórmula de 22/10) ou 2 (com agente e a_mando_de)."""
    try:
        return int(linha.get("hash_versao") or 1)
    except (TypeError, ValueError):
        return 1


def hash_da_linha(linha: dict, anterior: str | None) -> str:
    """O mesmo texto que o gatilho monta, com o mesmo SHA-256."""
    partes = ["" if linha.get(c) is None else str(linha.get(c)) for c in CAMPOS]
    partes.append(anterior or "")
    if versao_da_linha(linha) >= 2:
        partes.extend("" if linha.get(c) is None else str(linha.get(c))
                      for c in CAMPOS_DA_VERSAO_2)
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()


def divergencias(linhas: list[dict], semente: str | None = None) -> list[dict]:
    """As linhas em que a corrente não fecha. `linhas` em ordem de `id`;
    `semente` é o `hash_linha` da última linha encadeada ANTES da primeira
    daqui (ou None quando a corrente começa nela).

    Três motivos, e cada um aponta para uma coisa diferente:
    - «sem hash»: linha inserida depois de a corrente existir e sem o gatilho
      — alguém o desligou, ou gravou por caminho que não passa pelo banco;
    - «não aponta a anterior»: linha apagada no meio, ou inserida por fora
      com um anterior inventado;
    - «conteúdo mudou»: a linha foi editada depois de gravada.
    As linhas anteriores à corrente (hash NULL antes da primeira encadeada)
    não acusam nada: a corrente começa onde começou.
    """
    fora: list[dict] = []
    ultimo = semente
    comecou = semente is not None
    for linha in linhas:
        h = linha.get("hash_linha")
        if not h:
            if comecou:
                fora.append({"id": linha.get("id"), "ts": linha.get("ts"),
                             "action": linha.get("action"), "motivo": "sem hash"})
            continue
        if (linha.get("hash_anterior") or None) != ultimo:
            fora.append({"id": linha.get("id"), "ts": linha.get("ts"),
                         "action": linha.get("action"), "motivo": "não aponta a anterior"})
        elif hash_da_linha(linha, ultimo) != h:
            fora.append({"id": linha.get("id"), "ts": linha.get("ts"),
                         "action": linha.get("action"), "motivo": "conteúdo mudou"})
        ultimo = h
        comecou = True
    return fora
